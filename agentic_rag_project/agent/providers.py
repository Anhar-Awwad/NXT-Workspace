import os
from typing import Optional
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.openai import OpenAIChatModel
import openai
from dotenv import load_dotenv


load_dotenv()


def get_llm_model(model_choice: Optional[str] = None) -> OpenAIChatModel:
    llm_choice = model_choice or os.getenv('LLM_CHOICE', 'gpt-4-turbo-preview')
    api_key = os.getenv('OPENAI_API_KEY', 'LLM_API_KEY')

    provider = OpenAIProvider(api_key=api_key)
    return OpenAIChatModel(llm_choice, provider=provider)


def get_embedding_client() -> openai.AsyncOpenAI:
    api_key = os.getenv('OPENAI_API_KEY')
    
    return openai.AsyncOpenAI(
        api_key=api_key
    )


def get_embedding_model() -> str:
    return os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')