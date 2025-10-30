import { useState, useRef } from 'react';

const useSDK = (setResults, onRequestComplete) => {
  const [isLoading, setLoading] = useState(false);
  const [runningDeepQueries, setRunningDeepQueries] = useState(new Set());
  const activeConnections = useRef(new Map()); // Map of requestId -> {eventSource, resultIndex}
  const requestIdCounter = useRef(0);

  const parseQueryFromMessage = (message) => {
    const match = message.match(/(Querying the Denodo AI SDK for|Starting DeepQuery analysis for):\s*\*\*(.*?)\*\*/);
    return match ? match[2].replace(/\.$/, '').replace(/\n/g, '') : null;
  };

  const processQuestion = async (question, type, resultIndex) => {
    setLoading(true);
    
    // Generate unique request ID
    const requestId = `${type}_${Date.now()}_${++requestIdCounter.current}`;
    try {
      const eventSource = new EventSource(`question?query=${encodeURIComponent(question)}&type=${type}`);
      
      // Store the connection for potential cancellation
      activeConnections.current.set(requestId, { eventSource, resultIndex });

      let isStreamOff = false;
      let completedSuccessfully = false;

      eventSource.onmessage = (event) => {
        const data = event.data;

        if (data.startsWith("<TOOL:")) {
          const newQuestionType = data.split(":")[1].replace(">", "");
          
          // DeepQuery tracking - ONLY on TOOL:deep_query detection
          if (newQuestionType === "deep_query") {            
            setRunningDeepQueries(prev => {
              const newSet = new Set([...prev, requestId]);
              return newSet;
            });
          }
          
          setResults((prevResults) => {
            const updatedResults = prevResults.map((result, index) =>
              index === resultIndex
                ? { ...result, questionType: newQuestionType, queryPhase: "waiting" }
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
                      isShowingQuery: false,
                      queryPhase: "complete",
                      vql: jsonData.vql,
                      data_sources: jsonData.data_sources,
                      chatbot_llm: jsonData.chatbot_llm,
                      embeddings: jsonData.embeddings,
                      relatedQuestions: jsonData.related_questions,
                      relatedQuestionsDeepQuery: jsonData.related_questions_deepquery,
                      query_explanation: jsonData.query_explanation,
                      execution_result: jsonData.execution_result,
                      tables_used: jsonData.tables_used,
                      tokens: jsonData.tokens,
                      ai_sdk_time: jsonData.ai_sdk_time,
                      uuid: jsonData.uuid,
                      ...(jsonData.graph && { graph: jsonData.graph }),
                      ...(jsonData.pdf_url && { pdf_url: jsonData.pdf_url }),
                      ...(jsonData.pdf_path && { pdf_path: jsonData.pdf_path }),
                      ...(jsonData.deepquery_metadata && { deepquery_metadata: jsonData.deepquery_metadata }),
                      ...(jsonData.total_execution_time && { total_execution_time: jsonData.total_execution_time }),
                    }
                  : result
              );
              return updatedResults;
            });
            
            completedSuccessfully = true;

            // Clean up connection and DeepQuery tracking
            activeConnections.current.delete(requestId);
            setRunningDeepQueries(prev => {
              const newSet = new Set(prev);
              newSet.delete(requestId);
              return newSet;
            });
            eventSource.close();
          } catch (e) {
            setResults((prevResults) =>
              prevResults.map((result, index) =>
                index === resultIndex
                  ? { 
                      ...result, 
                      isLoading: false, 
                      result: "Error: Failed to parse response data. Details: " + e.message 
                    }
                  : result
              )
            );
            completedSuccessfully = false;
          } finally {
            onRequestComplete(requestId);
            setLoading(false);
          }
        } else {
          const extractedQuery = parseQueryFromMessage(data);
          
          if (extractedQuery) {
            setResults((prevResults) => {
              const updatedResults = prevResults.map((result, index) =>
                index === resultIndex
                  ? { 
                      ...result, 
                      isShowingQuery: true, 
                      intermediateQuery: extractedQuery,
                      queryPhase: "query"
                    }
                  : result
              );
              return updatedResults;
            });
          } else {
            // Regular streaming content
            setResults((prevResults) => {
              const updatedResults = prevResults.map((result, index) => {
                if (index === resultIndex) {
                  const currentResult = result;
                  
                  // If this is the first content and we're in query phase, switch to streaming
                  if (currentResult.queryPhase === "query" && data.trim() && !data.startsWith("<")) {
                    return { 
                      ...currentResult, 
                      queryPhase: "streaming",
                      result: currentResult.result + data.replace(/<NEWLINE>/g, '\n') 
                    };
                  } else {
                    // Continue accumulating content
                    return { 
                      ...currentResult, 
                      result: currentResult.result + data.replace(/<NEWLINE>/g, '\n') 
                    };
                  }
                }
                return result;
              });
              return updatedResults;
            });
          }
        }
      };
      
      eventSource.onerror = (err) => {        
        // Only treat as error if we haven't successfully completed
        if (!completedSuccessfully) {
          eventSource.close();

          // Update the result to show an appropriate error message
          setResults((prevResults) =>
            prevResults.map((result, index) =>
              index === resultIndex
                ? { 
                    ...result, 
                    isLoading: false, 
                    result: err.message,
                    queryPhase: "complete"
                  }
                : result
            )
          );
          
          activeConnections.current.delete(requestId);
          setRunningDeepQueries(prev => {
            const newSet = new Set(prev);
            newSet.delete(requestId);
            return newSet;
          });
          onRequestComplete(requestId);
        } else {
          eventSource.close();
        }
        setLoading(false);
      };
      
      eventSource.onopen = () => {};
      
      return requestId; // Return the request ID so the caller can track it
    } catch (error) {
      setResults((prevResults) =>
        prevResults.map((result, index) =>
          index === resultIndex
            ? { ...result, isLoading: false, result: "An error occurred while processing the question." }
            : result
        )
      );
      activeConnections.current.delete(requestId);
      setRunningDeepQueries(prev => {
        const newSet = new Set(prev);
        newSet.delete(requestId);
        return newSet;
      });
      onRequestComplete(requestId);
      setLoading(false);
      return null;
    }
  };

  const cancelDeepQuery = (requestId) => {    
    const connection = activeConnections.current.get(requestId);
    if (connection) {
      const { eventSource, resultIndex } = connection;
      
      eventSource.close();
      activeConnections.current.delete(requestId);
      
      // Remove the cancelled result from the results array
      setResults((prevResults) => {
        const filteredResults = prevResults.filter((_, index) => index !== resultIndex);
        return filteredResults;
      });
      
      // Update running DeepQueries
      setRunningDeepQueries(prev => {
        const newSet = new Set(prev);
        newSet.delete(requestId);
        return newSet;
      });
      onRequestComplete(requestId);
      setLoading(false);
    }
  };

  return { 
    isLoading, 
    processQuestion, 
    cancelDeepQuery, 
    runningDeepQueries: Array.from(runningDeepQueries) 
  };
};

export default useSDK;