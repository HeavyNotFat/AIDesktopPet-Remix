import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .llm import LLMError, generate


class ChatRequest(BaseModel):
    model: str
    question: str


api = APIRouter(prefix='/api')


@api.post('/getmodelname')
def get_model_name():
    return {'name': config.ASSISTANT_NAME}


@api.post('/getmodellist')
def get_model_list():
    return {'models': config.MODELS}


@api.post('/chat')
def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail='问题不能为空')

    if req.model not in {m['value'] for m in config.MODELS}:
        raise HTTPException(status_code=400, detail=f'未知模型：{req.model}')

    try:
        answer = generate(req.model, question)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {'answer': answer}


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