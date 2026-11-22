"""The generation prompt must use the date of the current request."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

from langchain_core.runnables import RunnableLambda

from api.utils.data_category import generate


def test_generation_date_refreshes_between_requests(monkeypatch):
    prompts = []

    class Clock:
        current = datetime(2026, 10, 23, 12)

        @classmethod
        def now(cls):
            return cls.current

    def capture_prompt(prompt):
        prompts.append(prompt.to_messages()[-1].content)
        return '<thoughts>Test response.</thoughts><vql>SELECT 1</vql>'

    monkeypatch.setattr(generate, 'datetime', Clock)
    monkeypatch.setattr('utils.langfuse.build_config', lambda **kwargs: {})
    llm = SimpleNamespace(
        llm=RunnableLambda(capture_prompt), provider_name='test', model_name='test'
    )

    async def run():
        await generate.query_to_vql('Show yesterday\'s payments', [], llm)
        Clock.current = datetime(2026, 10, 30, 12)
        await generate.query_to_vql('Show yesterday\'s payments', [], llm)

    asyncio.run(run())

    dates = [prompt.split('<date>')[1].split('</date>')[0].strip() for prompt in prompts]
    assert dates == ['2026-10-23', '2026-10-30']
