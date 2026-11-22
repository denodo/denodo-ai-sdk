import asyncio
import logging
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.runnables import RunnableLambda

from api.utils.ai_tools import category_detection as selection
from api.utils.data_category import generate


def model(fn):
    return SimpleNamespace(llm=RunnableLambda(fn), provider_name='test', model_name='model')


@pytest.mark.parametrize('ambiguity', [True, False])
def test_selection_uses_chat_roles_and_preserves_table_tags_tokens_and_explanation(caplog, ambiguity):
    prompts = []

    def capture(prompt):
        prompts.append(prompt.to_messages())
        return prompt

    response = AIMessage(
        content='<selection_thoughts>Customers provides the name.</selection_thoughts>'
                '<query><table>"demo"."customers"</table><text>1</text></query>',
        usage_metadata={'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15},
        response_metadata={'model_name': 'test'},
    )
    llm = SimpleNamespace(
        llm=RunnableLambda(capture) | FakeMessagesListChatModel(responses=[response]),
        provider_name='test', model_name='model',
    )

    with caplog.at_level(logging.INFO):
        category, result, questions, tokens = asyncio.run(selection.direct_sql_category(
            'Find Alice', [], llm, check_ambiguity=ambiguity,
        ))
    assert [message.type for message in prompts[0]] == ['system', 'human']
    assert 'Find Alice' not in prompts[0][0].content
    assert 'Find Alice' in prompts[0][1].content
    assert category == 'SQL'
    assert result == '<table>"demo"."customers"</table><text>1</text>'
    assert questions == []
    assert tokens['total_tokens'] == 15
    assert 'Selection LLM' in caplog.text
    assert 'Customers provides the name.' in caplog.text
    assert 'status=completed' in caplog.text


def test_no_suitable_view_does_not_call_generation_model():
    def unexpected_call(prompt):
        pytest.fail('No matching views must not fall back to all schema or call the LLM')

    result = asyncio.run(generate.query_to_vql(
        'Employee salaries', [], model(unexpected_call), filter_params='<table>None</table>',
    ))
    assert result.status == generate.GenerationStatus.NO_QUERY
    assert result.vql == ''
    assert result.tokens['total_tokens'] == 0


@pytest.mark.parametrize('kind', ['generation', 'selection', 'explicit_views'])
@pytest.mark.parametrize('outcome', ['completed', 'failed', 'cancelled'])
def test_model_activity_records_outcome_without_swallowing_errors(caplog, kind, outcome):
    def respond(prompt):
        if outcome == 'failed':
            raise RuntimeError('model unavailable')
        if outcome == 'cancelled':
            raise asyncio.CancelledError()
        return '<thoughts>Explanation.</thoughts><query><dates>1</dates></query><vql>SELECT 1</vql>'

    fn = {'generation': generate.query_to_vql,
          'selection': selection.direct_sql_category,
          'explicit_views': selection.direct_sql_parts}[kind]
    with caplog.at_level(logging.INFO):
        if outcome == 'completed':
            asyncio.run(fn('Question', [], model(respond)))
        else:
            error = RuntimeError if outcome == 'failed' else asyncio.CancelledError
            with pytest.raises(error):
                asyncio.run(fn('Question', [], model(respond)))
    role = 'Generation LLM' if kind == 'generation' else 'Selection LLM'
    assert f'{role} (provider=test, model=model) started.' in caplog.text
    assert f'finished (status={outcome})' in caplog.text
    if outcome == 'completed':
        assert 'Explanation.' in caplog.text


def test_explicit_view_flow_keeps_requested_views_and_parses_helper_tags():
    response = '<query><dates>1</dates></query>'
    decision = asyncio.run(selection.direct_sql_parts('Recent orders', [], model(lambda p: response)))
    enriched = selection.inject_selected_tables(decision[1], ['demo.orders'])
    assert '<table>demo.orders</table>' in enriched
    assert '<dates>1</dates>' in enriched


@pytest.mark.parametrize('winner', ['metadata', 'sql', 'failure'])
def test_category_race_waits_for_losing_task_cleanup(monkeypatch, winner):
    async def run():
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def slow():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        async def metadata(**kwargs):
            if winner == 'metadata':
                await started.wait()
                return 'METADATA', 'answer', [], {}
            return await slow()

        async def sql(prompt):
            if winner == 'metadata':
                return await slow()
            await started.wait()
            if winner == 'failure':
                raise RuntimeError('model unavailable')
            return '<cat>SQL</cat><query><table>demo.orders</table></query>'

        monkeypatch.setattr(selection, 'metadata_category', metadata)
        if winner == 'failure':
            with pytest.raises(RuntimeError, match='model unavailable'):
                await selection.sql_category('Question', [], model(sql))
        else:
            result = await selection.sql_category('Question', [], model(sql))
            assert result[0] == ('METADATA' if winner == 'metadata' else 'SQL')
        assert cleaned.is_set(), 'Child calls must finish before returning from classification'

    asyncio.run(asyncio.wait_for(run(), timeout=5))
