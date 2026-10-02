import React, { createContext, useState, useContext, useEffect } from 'react';
import api from '../api/client';
import { getNumberFormat, formatNumber } from '../utils/numberFormat';

// Create the context
const ConfigContext = createContext();

// Returns the input method saved by the user in the User Profile modal, if any
export const getSavedInputMethod = (username) => {
  const user = username || localStorage.getItem('current_user');
  const saved = user && localStorage.getItem(`${user}_input_method`);
  return ['enter', 'ctrl_enter'].includes(saved) ? saved : null;
};

// Create a provider component
export const ConfigProvider = ({ children }) => {
  const [config, setConfig] = useState({
    // No default values - we'll only use what the server provides
  });
  const [loading, setLoading] = useState(true);

  const updateConfig = (newParams) => {
    setConfig(prev => ({ ...prev, ...newParams }));
  };

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await api.get("config");
        const savedInputMethod = getSavedInputMethod();
        setConfig({
          ...response.data,
          ...(savedInputMethod ? { input_method: savedInputMethod } : {}),
          number_format: getNumberFormat(),
        });
      } catch (error) {
        console.error('Error fetching config:', error);
        // Keep empty config if fetch fails
      } finally {
        setLoading(false);
      }
    };

    fetchConfig();
  }, []);

  return (
    <ConfigContext.Provider value={{ config, loading, updateConfig }}>
      {children}
    </ConfigContext.Provider>
  );
};

// Create a custom hook to use the config context
export const useConfig = () => {
  const context = useContext(ConfigContext);
  if (context === undefined) {
    throw new Error('useConfig must be used within a ConfigProvider');
  }
  return context;
};

// Returns a formatter that uses the number format chosen in the User Profile modal
export const useNumberFormat = () => {
  const { config } = useConfig();
  return (value, decimals = 0) => formatNumber(value, config.number_format, decimals);
};

export default ConfigContext;
