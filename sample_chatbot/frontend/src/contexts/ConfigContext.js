import React, { createContext, useState, useContext, useEffect } from 'react';
import api from '../api/client';

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
        setConfig(savedInputMethod
          ? { ...response.data, input_method: savedInputMethod }
          : response.data);
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

export default ConfigContext; 
