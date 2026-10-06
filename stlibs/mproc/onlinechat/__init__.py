import logging

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .llm import SessionClosedError, pool
from .registry import UnknownModelError
from .registry import registry as model_registry

logger = logging.getLogger('onlinechat')


class ChatRequest(BaseModel):
    model: str
    question: str
    #: 前端每条会话一个 id；不传则共用 ``default`` 会话（兼容旧客户端）
    session_id: str | None = Field(default=None, max_length=128)


class SessionRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)


api = APIRouter(prefix='/api')


@api.post('/getmodelname')
def get_model_name():
    return {'name': config.ASSISTANT_NAME}


@api.post('/getmodellist')
def get_model_list():
    targets = model_registry.snapshot()
    return {'models': [target.public() for target in targets.values()]}


@api.post('/chat')
def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail='问题不能为空')

    try:
        answer = pool.chat(req.model, question, req.session_id)
    except UnknownModelError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SessionClosedError as e:
        # 会话刚好被 TTL/LRU/删除对话回收掉：让前端重发一次即可，不算服务端故障
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 - 统一转成 502 给前端展示
        logger.exception('网页聊天生成失败')
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}") from e

    return {'answer': answer}


@api.post('/reset')
def reset(req: SessionRequest):
    """丢弃会话实例（网页端「删除对话」时调用）。"""
    dropped = pool.reset(req.session_id)
    return {'dropped': dropped}


@api.post('/status')
def status():
    """实例池观测接口：CI/排障时确认网页端确实用的是自己的实例。"""
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
