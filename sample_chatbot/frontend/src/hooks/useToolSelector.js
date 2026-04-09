import { useMemo, useCallback } from "react";

const normalizeString = (value) =>
  String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/_/g, "")
    .replace(/@/g, "");

const useToolSelector = (config) => {
  const availableTools = useMemo(() => {
    const tools = Array.isArray(config?.chatbot_tools) ? config.chatbot_tools : [];
    
    return tools.filter(tool => {
      if (tool.name === 'deep_query' && !config?.enable_deep_query) return false;
      if (tool.name === 'kb' && !config?.unstructured_mode) return false;
      return true;
    });
  }, [config]);

  const resolveToolFromToken = useCallback(
    (rawToken) => {
      if (!rawToken) return null;
      const token = normalizeString(
        rawToken.startsWith("@") ? rawToken.slice(1) : rawToken
      );

      for (const tool of availableTools) {
        if (tool.name && normalizeString(tool.name) === token) return tool;
        if (Array.isArray(tool.aliases)) {
          if (
            tool.aliases.some(
              (alias) => normalizeString(alias) === token
            )
          ) {
            return tool;
          }
        }
      }
      return null;
    },
    [availableTools]
  );

  const prepareSubmission = useCallback(
    (questionText, forcedTool) => {
      const trimmedStart = questionText.replace(/^\s*/, "");
      let toolName = forcedTool || null;
      let toolPrettyName = null;
      let finalQuestion = questionText.trim();

      if (trimmedStart.startsWith("@")) {
        const match = trimmedStart.match(/^@(\S*)/);
        const token = match ? match[1] : "";
        const resolvedTool = token ? resolveToolFromToken(token) : null;
        
        if (resolvedTool) {
          toolName = resolvedTool.name;
          toolPrettyName = resolvedTool.pretty_name || resolvedTool.name;
          finalQuestion = questionText.replace(/^@\S+\s*/, "").trim();
        }
      }

      if (toolName && !toolPrettyName) {
        const matched = availableTools.find((tool) => tool.name === toolName);
        if (matched) {
          toolPrettyName = matched.pretty_name || matched.name;
        } else {
          toolPrettyName = toolName;
        }
      }

      return { finalQuestion, toolName, toolPrettyName };
    },
    [resolveToolFromToken, availableTools]
  );

  return {
    prepareSubmission,
  };
};

export default useToolSelector;
