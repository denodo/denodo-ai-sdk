import React, { createContext, useState, useContext, useEffect } from 'react';
import api from '../api/client';
import { getNumberFormat, formatNumber } from '../utils/numberFormat';

// Create the context
const ConfigContext = createContext();

const emptyProfile = () => ({
  user_details: '',
  input_method: 'enter',
  number_format: getNumberFormat(),
});

// Create a provider component
export const ConfigProvider = ({ children }) => {
  const [config, setConfig] = useState({
    // No default values - we'll only use what the server provides
  });
  // Profile is per user (details, input method, number format). It stays off
  // `config`, which /api/config replaces with the agent settings.
  const [profile, setProfile] = useState(emptyProfile);
  const [loading, setLoading] = useState(true);

  const updateConfig = (newParams) => {
    setConfig(prev => ({ ...prev, ...newParams }));
  };

  const updateProfile = (newParams) => {
    setProfile(prev => ({
      ...prev,
      ...newParams,
      number_format: newParams.number_format || prev.number_format,
    }));
  };

  const clearProfile = () => {
    setProfile(emptyProfile());
  };

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await api.get("config");
        setConfig({ ...response.data });
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
    <ConfigContext.Provider value={{ config, profile, loading, updateConfig, updateProfile, clearProfile }}>
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
  const { profile } = useConfig();
  return (value, decimals = 0) => formatNumber(value, profile.number_format, decimals);
};

export default ConfigContext;
