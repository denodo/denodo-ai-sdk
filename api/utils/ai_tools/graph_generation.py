import asyncio
import inspect
import json
import logging

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_experimental.utilities import PythonREPL

from utils import langfuse
from utils import utils
from api.utils import sdk_utils
from api.utils.ai_tools.prompts import (
    GENERATE_VISUALIZATION_PROMPT,
    GENERATE_VISUALIZATION_PYTHON_TEMPLATE,
)
from api.utils.ai_tools.types import empty_tokens


def _usage_tokens(callback):
    return next(iter(callback.usage_metadata.values())) if callback.usage_metadata else empty_tokens()


@utils.log_params
@utils.timed
async def graph_generator(
    query, plot_data, llm,
    details='No special requirements',
    session_id=None
):
    final_prompt = PromptTemplate.from_template(GENERATE_VISUALIZATION_PROMPT)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    execution_result_df = sdk_utils.execution_result_to_dataframe(plot_data)
    data_stats = sdk_utils.dataframe_stats(execution_result_df)

    with get_usage_metadata_callback() as cb:
        response = await final_chain.ainvoke(
            {
                "instruction": query,
                "plot_details": details,
                "sample_data": json.dumps(execution_result_df[:3].to_dict(orient='records')),
                "sample_data_stats": data_stats
            },
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    response = response.replace('```python', '<python>').replace('```', '</python>').strip()
    python_code = utils.custom_tag_parser(response, 'python', default='')[0].strip()
    tokens = _usage_tokens(cb)

    if not python_code:
        return "LLM failed to generate a valid Python code, please try again.", tokens

    python_code = GENERATE_VISUALIZATION_PYTHON_TEMPLATE.format(python_code=python_code)
    python_repl = PythonREPL(_locals={"data": execution_result_df})
    output = await asyncio.to_thread(python_repl.run, python_code)

    if not output.startswith('data:image'):
        logging.error(f"LLM failed to generate a valid Python code, please try again. LLM output: {output}")
        return "LLM failed to generate a valid Python code, please try again.", tokens

    if output.endswith("\n"):
        output = output[:-1]

    return output, tokens
