// localStorage key for CSV configs
const CSV_STORAGE_KEY = 'chatbot_csv_sources';

// Helper functions for localStorage
export const getStoredCSVConfigs = (username) => {
  try {
    const stored = localStorage.getItem(`${username}_${CSV_STORAGE_KEY}`);
    return stored ? JSON.parse(stored) : [];
  } catch (e) {
    console.error('Error reading CSV configs from localStorage:', e);
    return [];
  }
};

export const saveCSVConfigs = (username, configs) => {
  try {
    localStorage.setItem(`${username}_${CSV_STORAGE_KEY}`, JSON.stringify(configs));
  } catch (e) {
    console.error('Error saving CSV configs to localStorage:', e);
  }
};

// Helper function to format delimiter label
export const getDelimiterLabel = (delimiter) => {
  if (delimiter === ',') return 'comma (,)';
  if (delimiter === ';') return 'semicolon (;)';
  return `"${delimiter}"`;
};
