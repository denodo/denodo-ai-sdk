// Number formats the user can pick in the User Profile modal.
// The key is both the label shown in the dropdown and the value saved in localStorage.
export const NUMBER_FORMATS = {
  '1,234.56': { thousands: ',', decimal: '.' },
  '1.234,56': { thousands: '.', decimal: ',' },
};

export const DEFAULT_NUMBER_FORMAT = '1,234.56';

// Picks the number format that matches the browser locale.
// The decimal separator is checked instead of the thousands separator because some locales
// do not group four-digit numbers (es-ES shows 1000, not 1.000) and others group with a space
// or an apostrophe (fr-FR, de-CH) while still using a comma as the decimal separator.
export const inferNumberFormat = () => {
  try {
    const decimal = new Intl.NumberFormat().formatToParts(1.5).find((part) => part.type === 'decimal');
    return decimal?.value === ',' ? '1.234,56' : '1,234.56';
  } catch {
    return DEFAULT_NUMBER_FORMAT;
  }
};

// Returns the number format saved in the User Profile modal, if any
export const getSavedNumberFormat = (username) => {
  const user = username || localStorage.getItem('current_user');
  const saved = user && localStorage.getItem(`${user}_number_format`);
  return Object.keys(NUMBER_FORMATS).includes(saved) ? saved : null;
};

export const getNumberFormat = (username) => {
  return getSavedNumberFormat(username) || inferNumberFormat();
};

// Formats a number with the thousands and decimal separators of the given number format.
// Returns null when the value is not a number so callers can show their own fallback.
export const formatNumber = (value, numberFormat, decimals = 0) => {
  if (value == null || value === '') return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;

  const separators = NUMBER_FORMATS[numberFormat] || NUMBER_FORMATS[DEFAULT_NUMBER_FORMAT];
  const enUS = number.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return enUS.replace(/[,.]/g, (char) => (char === ',' ? separators.thousands : separators.decimal));
};
