import json
import logging
import threading

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .llm import SessionClosedError, pool
from .registry import UnknownModelError
from .registry import registry as model_registry

logger = logging.getLogger('onlinechat')


class AttachmentIn(BaseModel):
    name: str = Field(default="", max_length=200)
    mime: str = Field(default="", max_length=120)
    # 前端统一按 base64 上传
    data: str = Field(default="", max_length=config.MAX_ATTACHMENT_CHARS)


class ChatRequest(BaseModel):
    model: str
    question: str = ""
    session_id: str | None = Field(default=None, max_length=128)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=config.MAX_ATTACHMENTS)


class SessionRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)


class RecallRequest(BaseModel):
    model: str
    question: str
    answer: str
    session_id: str | None = Field(default=None, max_length=128)


api = APIRouter(prefix='/api')

SSE_HEADERS = {
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _validate(req: ChatRequest) -> str:
    question = req.question.strip()
    if not question and not req.attachments:
        raise HTTPException(status_code=400, detail='问题不能为空')
    return question


def _attachments(req: ChatRequest) -> list:
    """把上传的 base64 统一成附件字典。"""
    if not req.attachments:
        return []

    from ...ai import attachment

    items = [item.model_dump() for item in req.attachments]
    result = attachment.normalize(items)
    if not result:
        raise HTTPException(status_code=400, detail='附件无法解析（可能为空或格式不对）')
    return result


@api.post('/getmodelname')
def get_model_name():
    return {'name': config.ASSISTANT_NAME}


@api.post('/getmodellist')
def get_model_list():
    targets = model_registry.snapshot()
    return {'models': [target.public() for target in targets.values()]}


def _plugin_prompt() -> str:
    """插件要求的系统提示词，让网页聊天与本地聊天行为一致。"""
    try:
        from ... import plugin_prompts

        return "\n\n".join(plugin_prompts())
    except Exception:  # noqa: BLE001 - 插件坏了不能挡住聊天
        return ""


@api.post('/chat')
def chat(req: ChatRequest):
    question = _validate(req)
    attachments = _attachments(req)

    try:
        answer = pool.chat(req.model, question, req.session_id, attachments,
                           skill=_plugin_prompt() or None)
    except UnknownModelError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SessionClosedError as e:
        # 会话刚被回收：让前端重发一次即可
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 - 统一转成 502 给前端
        logger.exception('网页聊天生成失败')
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}") from e

    return {'answer': answer}


@api.post('/chat/stream')
def chat_stream(req: ChatRequest):
    question = _validate(req)
    attachments = _attachments(req)
    stop_event = threading.Event()

    try:
        chunks = pool.stream(req.model, question, req.session_id, stop_event=stop_event,
                             attachments=attachments, skill=_plugin_prompt() or None)
    except UnknownModelError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SessionClosedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception('网页聊天流式生成无法启动')
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}") from e

    def events():
        yield _sse({'type': 'start', 'session_id': req.session_id})
        try:
            for chunk in chunks:
                yield _sse({'type': 'delta', 'text': chunk})
        except SessionClosedError as e:
            yield _sse({'type': 'error', 'detail': str(e), 'retry': True})
            return
        except Exception as e:  # noqa: BLE001
            logger.exception('网页聊天流式生成中断')
            yield _sse({'type': 'error', 'detail': f"{type(e).__name__}: {e}"})
            return
        finally:
            stop_event.set()

        yield _sse({'type': 'done'})

    return StreamingResponse(events(), media_type='text/event-stream', headers=SSE_HEADERS)


@api.post('/chat/recall')
def chat_recall(req: RecallRequest):
    """补记一轮没走模型的问答。"""
    question = req.question.strip()
    if not question or not req.answer.strip():
        raise HTTPException(status_code=400, detail='问题与回答都不能为空')

    try:
        recorded = pool.remember(req.model, question, req.answer, req.session_id)
    except UnknownModelError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SessionClosedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception('补记缓存问答失败')
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}") from e

    return {'recorded': recorded}


@api.post('/reset')
def reset(req: SessionRequest):
    dropped = pool.reset(req.session_id)
    return {'dropped': dropped}


@api.post('/status')
def status():
    return {
        'assistant': config.ASSISTANT_NAME,
        'models': len(model_registry.snapshot()),
        'pool': pool.stats(),
    }


@api.get('/health', include_in_schema=False)
def health():
    return {'ok': True}


app = FastAPI(title='AI Desktop Pet - OnlineChat')
app.include_router(api)


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(config.WEB_DIR / 'index.html')


app.mount('/css', StaticFiles(directory=config.WEB_DIR / 'css'), name='css')
app.mount('/js', StaticFiles(directory=config.WEB_DIR / 'js'), name='js')


def main():
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == '__main__':
    main()
