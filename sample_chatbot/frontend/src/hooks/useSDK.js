import { useState } from 'react';

const useSDK = (setResults) => {
  const [isLoading, setLoading] = useState(false);

  const processQuestion = async (question, type, resultIndex) => {
    setLoading(true);

    try {
      const eventSource = new EventSource(`question?query=${encodeURIComponent(question)}&type=${type}`);
      let isStreamOff = false;
      let context = null;
      let relatedTables = null;

      eventSource.onmessage = (event) => {
        const data = event.data;

        if (data.startsWith("<TOOL:")) {
          const newQuestionType = data.split(":")[1].replace(">", "");
          setResults((prevResults) => {
            const updatedResults = prevResults.map((result, index) =>
              index === resultIndex
                ? { ...result, questionType: newQuestionType }
                : result
            );
            return updatedResults;
          });
          return;
        }      
        
        if (data === "<STREAMOFF>") {
          isStreamOff = true;
          return;
        }

        if (isStreamOff) {
          try {
            const jsonData = JSON.parse(data);
            setResults((prevResults) => {
              const updatedResults = prevResults.map((result, index) =>
                index === resultIndex
                  ? {
                      ...result,
                      isLoading: false,
                      vql: jsonData.vql,
                      data_sources: jsonData.data_sources,
                      embeddings: jsonData.embeddings,
                      relatedQuestions: jsonData.related_questions,
                      query_explanation: jsonData.query_explanation,
                      execution_result: jsonData.execution_result,
                      tables_used: jsonData.tables_used,
                      context: context,
                      relatedTables: relatedTables,
                      tokens: jsonData.tokens,
                      ai_sdk_time: jsonData.ai_sdk_time,
                      uuid: jsonData.uuid,
                      ...(jsonData.graph && { graph: jsonData.graph }),
                    }
                  : result
              );
              return updatedResults;
            });
          } catch (e) {
            console.error("Failed to parse JSON data:", e);
          }
        } else {
          setResults((prevResults) => {
            const updatedResults = prevResults.map((result, index) =>
              index === resultIndex
                ? { ...result, result: result.result + data.replace(/<NEWLINE>/g, '\n') }
                : result
            );
            return updatedResults;
          });
        }
      };
      
      eventSource.onerror = (err) => {
        eventSource.close();
        setLoading(false);
      };
      
      eventSource.onopen = () => {
        console.log("EventSource connection opened");
      };
    } catch (error) {
      console.error("Error in processQuestion:", error);
      setResults((prevResults) =>
        prevResults.map((result, index) =>
          index === resultIndex
            ? { ...result, isLoading: false, result: "An error occurred while processing the question." }
            : result
        )
      );
      setLoading(false);
    }

    setLoading(false);
  };

  return { isLoading, processQuestion };
};

export default useSDK;