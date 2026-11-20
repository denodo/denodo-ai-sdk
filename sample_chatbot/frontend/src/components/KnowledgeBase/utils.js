// Helper function to format delimiter label
export const getDelimiterLabel = (delimiter) => {
  if (delimiter === ',') return 'comma (,)';
  if (delimiter === ';') return 'semicolon (;)';
  return `"${delimiter}"`;
};
