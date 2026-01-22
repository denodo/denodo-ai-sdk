import { useMemo, useCallback } from "react";

const normalizeString = (value) =>
  String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/_/g, "")
    .replace(/@/g, "");

const useToolSelector = (config) => {
  const availableTools = useMemo(
    () => (Array.isArray(config?.chatbotTools) ? config.chatbotTools : []),
    [config]
  );

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
          toolPrettyName = resolvedTool.prettyName || resolvedTool.name;
        }

        finalQuestion = questionText.replace(/^@\S+\s*/, "").trim();
      }

      // If the tool was forced (e.g. DeepQuery button), try to resolve a pretty name
      if (toolName && !toolPrettyName) {
        const matched = availableTools.find((tool) => tool.name === toolName);
        if (matched) {
          toolPrettyName = matched.prettyName || matched.name;
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


