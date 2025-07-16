import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';

// Create the context
const ConfigContext = createContext();

// Create a provider component
export const ConfigProvider = ({ children }) => {
  const [config, setConfig] = useState({
    // No default values - we'll only use what the server provides
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await axios.get('api/config');
        setConfig(response.data);
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
    <ConfigContext.Provider value={{ config, loading }}>
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