import React, { useState } from 'react';
import Badge from 'react-bootstrap/Badge';
import './ChipInput.css';

const ChipInput = ({ items, setItems, placeholder, id }) => {
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addCurrentItem();
    } 
    else if ((e.key === 'Backspace' || e.key === 'Delete') && inputValue === '' && items.length > 0) {
      e.preventDefault();
      setItems(items.slice(0, -1));
    }
  };

  const handleBlur = () => {
    addCurrentItem();
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const paste = e.clipboardData.getData('text');
    if (paste) {
      const pastedItems = paste.split(/\r?\n/).map(s => s.trim()).filter(s => s);
      if (pastedItems.length > 0) {
        const uniqueItems = Array.from(new Set([...items, ...pastedItems]));
        setItems(uniqueItems);
      }
    }
  };

  const addCurrentItem = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !items.includes(trimmed)) {
      setItems([...items, trimmed]);
    }
    setInputValue('');
  };

  const removeItem = (itemToRemove) => {
    setItems(items.filter(item => item !== itemToRemove));
  };

  return (
    <div 
      className="form-control d-flex flex-wrap gap-2 align-items-center chip-input-container" 
      onClick={() => document.getElementById(id)?.focus()}
    >
      {items.map(item => (
        <Badge 
          key={item} 
          bg="secondary" 
          className="d-flex align-items-center px-2 py-1 chip-input-badge" 
        >
          {item}
          <button 
            type="button" 
            className="btn-close btn-close-white ms-2 chip-input-remove-btn" 
            onClick={(e) => { e.stopPropagation(); removeItem(item); }}
            aria-label="Remove"
          />
        </Badge>
      ))}
      <input
        id={id}
        type="text"
        className="border-0 flex-grow-1 bg-transparent chip-input-field"
        placeholder={items.length === 0 ? placeholder : ''}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        onPaste={handlePaste}
      />
    </div>
  );
};

export default ChipInput;
