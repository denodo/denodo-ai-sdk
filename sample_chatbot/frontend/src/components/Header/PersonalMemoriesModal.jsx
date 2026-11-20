import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import PropTypes from 'prop-types';
import { BaseModal, ConfirmationModal } from '../Common/Modal';
import Spinner from 'react-bootstrap/Spinner';
import Form from 'react-bootstrap/Form';
import Overlay from 'react-bootstrap/Overlay';
import Popover from 'react-bootstrap/Popover';
import api from '../../api/client';
import './PersonalMemoriesModal.css';

const emptyMemory = {
  memoryType: 'user',
  agentId: 'global',
  name: '',
  description: '',
  body: '',
  links: []
};

const MAX_DESCRIPTION_LENGTH = 1024;

const LINKED_TYPES = ['user-metadata', 'metadata'];

const TYPE_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'user', label: 'About you' },
  { id: 'user-metadata', label: 'Data preferences' },
  { id: 'metadata', label: 'Data facts' },
];

const TYPE_META = {
  user: { label: 'About you', icon: 'bi-person' },
  'user-metadata': { label: 'Data preferences', icon: 'bi-sliders' },
  metadata: { label: 'Data facts', icon: 'bi-database' },
};

const isLinkedType = (memoryType) => LINKED_TYPES.includes(memoryType);

const memoryKey = (memory) => `${memory.agent_id || 'global'}:${memory.type}:${memory.name}`;

const agentIdOf = (bot) => {
  if (!bot || bot.isGlobal || bot.id === 'global') return 'global';
  return bot.id;
};

const emptyLink = () => ({ kind: 'view', name: '' });

const FilterList = ({ values, options, onToggle, ariaLabel, emptyLabel }) => (
  <div className="mem-filter-list" role="group" aria-label={ariaLabel}>
    {options.length === 0 && emptyLabel ? (
      <p className="mem-filter-empty">{emptyLabel}</p>
    ) : options.map((option) => {
      const checked = values.includes(option.value);
      return (
        <label key={option.value} className={`mem-filter-option ${checked ? 'is-active' : ''}`}>
          <input
            type="checkbox"
            checked={checked}
            onChange={() => onToggle(option.value)}
          />
          {option.kind ? (
            <span className="mem-filter-link">
              <span className="mem-filter-kind">{kindWord(option.kind)}</span>
              <span className="mem-filter-name">{option.name}</span>
            </span>
          ) : (
            <span>{option.label}</span>
          )}
        </label>
      );
    })}
  </div>
);

FilterList.propTypes = {
  values: PropTypes.array.isRequired,
  options: PropTypes.array.isRequired,
  onToggle: PropTypes.func.isRequired,
  ariaLabel: PropTypes.string.isRequired,
  emptyLabel: PropTypes.string,
};

const linkFilterValue = (link) => `${link.kind}\n${link.name}`;

const KIND_ORDER = { view: 0, tag: 1, database: 2 };

const compareLinks = (left, right) => {
  const byKind = (KIND_ORDER[left.kind] ?? 9) - (KIND_ORDER[right.kind] ?? 9);
  if (byKind !== 0) return byKind;
  return String(left.name || '').localeCompare(String(right.name || ''));
};

const kindWord = (kind) => {
  if (kind === 'view') return 'View';
  if (kind === 'database') return 'Database';
  if (kind === 'tag') return 'Tag';
  return kind || '';
};

const formatUpdated = (value) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
};

const PersonalMemoriesModal = ({ show, handleClose, chatbots = [], selectedChatbot = null }) => {
  const [memories, setMemories] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [selectedAgents, setSelectedAgents] = useState([]);
  const [agentMatch, setAgentMatch] = useState('available');
  const [sharingAgentIds, setSharingAgentIds] = useState([]);
  const [selectedLinks, setSelectedLinks] = useState([]);
  const [linkQuery, setLinkQuery] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selectedKey, setSelectedKey] = useState(null);
  const [editingKey, setEditingKey] = useState(null);
  const [editingMemory, setEditingMemory] = useState(emptyMemory);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [deletingKeys, setDeletingKeys] = useState(() => new Set());
  const [confirmDelete, setConfirmDelete] = useState({ show: false, memory: null });
  const [showInfoBanner, setShowInfoBanner] = useState(true);
  const filterButtonRef = useRef(null);

  const agentName = useCallback((agentId) => {
    const id = agentId || 'global';
    const bot = chatbots.find((item) => agentIdOf(item) === id);
    if (bot?.name) return bot.name;
    return id === 'global' ? 'General chat' : id;
  }, [chatbots]);

  const audienceIds = useCallback((memory) => {
    const owner = memory.agent_id || 'global';
    if (memory.type === 'metadata') {
      const ids = chatbots.map((bot) => agentIdOf(bot));
      if (!ids.includes(owner)) ids.unshift(owner);
      return ids.length ? ids : [owner];
    }
    const ids = [owner];
    const canBeShared = owner === 'global' && (memory.type === 'user' || memory.type === 'user-metadata');
    if (canBeShared) {
      sharingAgentIds.forEach((id) => {
        if (!ids.includes(id)) ids.push(id);
      });
    }
    return ids;
  }, [sharingAgentIds, chatbots]);

  useEffect(() => {
    if (show) {
      setError(null);
      setSelectedKey(null);
      setEditingKey(null);
      setEditingMemory(emptyMemory);
      setQuery('');
      setTypeFilter('all');
      setSelectedAgents([]);
      setAgentMatch('available');
      setSelectedLinks([]);
      setLinkQuery('');
      setFiltersOpen(false);
      setShowInfoBanner(true);
    }
  }, [show]);

  const fetchMemories = useCallback(async () => {
    if (!show) return;
    setIsLoading(true);
    setError(null);
    try {
      const targets = chatbots.length ? chatbots : [selectedChatbot || { id: 'global', isGlobal: true }];
      const responses = await Promise.all(targets.map(async (bot) => {
        try {
          const response = await api.get('memories', { params: { agent_id: agentIdOf(bot) } });
          return { agentId: agentIdOf(bot), data: response.data };
        } catch (err) {
          if (err.response?.status === 403 || err.response?.status === 404) return null;
          throw err;
        }
      }));
      const seen = new Set();
      const merged = [];
      const sharing = [];
      responses.forEach((entry) => {
        if (!entry?.data?.success) return;
        if (entry.agentId !== 'global' && entry.data.share_general_memory) sharing.push(entry.agentId);
        (entry.data.memories || []).forEach((memory) => {
          const key = memoryKey(memory);
          if (seen.has(key)) return;
          seen.add(key);
          merged.push(memory);
        });
      });
      setMemories(merged);
      setSharingAgentIds(sharing);
    } catch (err) {
      setError('Failed to load memories');
      console.error('Error fetching memories:', err);
    } finally {
      setIsLoading(false);
    }
  }, [show, chatbots, selectedChatbot]);

  useEffect(() => { fetchMemories(); }, [fetchMemories]);

  useEffect(() => {
    if (!filtersOpen) return undefined;
    const onMouseDown = (event) => {
      if (event.target.closest && event.target.closest('.mem-filter-popover')) return;
      if (filterButtonRef.current && filterButtonRef.current.contains(event.target)) return;
      setFiltersOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [filtersOpen]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return memories
      .filter((memory) => {
        if (typeFilter !== 'all' && memory.type !== typeFilter) return false;
        const owner = memory.agent_id || 'global';
        if (selectedAgents.length && agentMatch === 'owner' && !selectedAgents.includes(owner)) return false;
        if (selectedAgents.length && agentMatch === 'available' && !selectedAgents.some((id) => audienceIds(memory).includes(id))) {
          return false;
        }
        const links = memory.links || [];
        if (selectedLinks.length && !links.some((link) => selectedLinks.includes(linkFilterValue(link)))) return false;
        if (!needle) return true;
        const haystack = [memory.name, memory.description, memory.body, ...links.map((link) => link.name)]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(needle);
      })
      .sort((left, right) => String(right.modified || '').localeCompare(String(left.modified || '')));
  }, [memories, query, typeFilter, selectedAgents, agentMatch, audienceIds, selectedLinks]);

  const filteredKey = filtered.map(memoryKey).join('|');

  const typeCounts = useMemo(() => {
    const counts = { all: memories.length };
    TYPE_FILTERS.forEach((option) => {
      if (option.id !== 'all') counts[option.id] = memories.filter((memory) => memory.type === option.id).length;
    });
    return counts;
  }, [memories]);

  useEffect(() => {
    if (!show || isLoading) return;
    setSelectedKey((current) => {
      if (!filtered.length) return null;
      if (current && filtered.some((memory) => memoryKey(memory) === current)) return current;
      return memoryKey(filtered[0]);
    });
  }, [show, isLoading, filteredKey]); // filtered is the list that produced filteredKey

  useEffect(() => {
    if (editingKey && editingKey !== selectedKey) {
      setEditingKey(null);
      setEditingMemory(emptyMemory);
    }
  }, [editingKey, selectedKey]);

  const selected = filtered.find((memory) => memoryKey(memory) === selectedKey) || null;
  const isEditing = Boolean(selected && editingKey === memoryKey(selected));

  const linkItemOptions = useMemo(() => {
    const seen = new Set();
    const options = [];
    memories.forEach((memory) => {
      (memory.links || []).forEach((link) => {
        if (!link.kind || !link.name) return;
        const value = linkFilterValue(link);
        if (seen.has(value)) return;
        seen.add(value);
        options.push({ value, kind: link.kind, name: link.name });
      });
    });
    options.sort(compareLinks);
    return options;
  }, [memories]);

  const visibleLinkOptions = useMemo(() => {
    const needle = linkQuery.trim().toLowerCase();
    if (!needle) return linkItemOptions;
    return linkItemOptions.filter((option) => option.name.toLowerCase().includes(needle));
  }, [linkItemOptions, linkQuery]);

  const activeFilterCount = selectedAgents.length + selectedLinks.length;

  const validateDescription = (description) => {
    const trimmed = (description || '').trim();
    if (!trimmed) { setError('Please provide a description'); return false; }
    if (trimmed.length > MAX_DESCRIPTION_LENGTH) {
      setError(`Description must be at most ${MAX_DESCRIPTION_LENGTH} characters`);
      return false;
    }
    return true;
  };

  const validateLinks = (memoryType, links) => {
    const filled = [];
    for (const link of links || []) {
      const name = (link.name || '').trim();
      if (!link.kind && !name) continue;
      if (!name) {
        setError('Please provide a link name');
        return null;
      }
      if (link.kind === 'view' && !/^[^\s.]+\.[^\s.]+$/.test(name)) {
        setError('A view link must be database.view_name');
        return null;
      }
      filled.push({ kind: link.kind, name });
    }
    if (memoryType === 'user' && filled.length > 0) {
      setError('A user memory cannot be linked. Use user-metadata for a personal preference about specific metadata');
      return null;
    }
    if (isLinkedType(memoryType) && filled.length === 0) {
      setError('A user-metadata or metadata memory must be linked to at least one view, database, or tag');
      return null;
    }
    return filled;
  };

  const selectMemory = (memory) => {
    const key = memoryKey(memory);
    if (key !== selectedKey) {
      setEditingKey(null);
      setEditingMemory(emptyMemory);
    }
    setSelectedKey(key);
  };

  const handleStartEdit = (memory) => {
    setSelectedKey(memoryKey(memory));
    setEditingKey(memoryKey(memory));
    const storedLinks = (memory.links || []).map((link) => ({ kind: link.kind, name: link.name }));
    setEditingMemory({
      memoryType: memory.type,
      agentId: memory.agent_id || 'global',
      name: memory.name,
      description: memory.description || '',
      body: (memory.body || '').replace(/\n$/, ''),
      links: storedLinks.length ? storedLinks : (isLinkedType(memory.type) ? [emptyLink()] : [])
    });
  };

  const handleSaveEdit = async () => {
    if (!validateDescription(editingMemory.description)) return;
    if (!editingMemory.body.trim()) { setError('Memory note cannot be empty'); return; }
    const links = validateLinks(editingMemory.memoryType, editingMemory.links);
    if (!links) return;

    setIsSavingEdit(true);
    setError(null);
    try {
      const response = await api.post('memories', {
        memory_type: editingMemory.memoryType,
        agent_id: editingMemory.agentId,
        name: editingMemory.name,
        description: editingMemory.description.trim(),
        body: editingMemory.body,
        links: editingMemory.memoryType === 'user' ? [] : links
      });
      if (response.data.success) {
        setEditingKey(null);
        setEditingMemory(emptyMemory);
        await fetchMemories();
      }
    } catch (err) {
      setError(`Failed to update memory: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsSavingEdit(false);
    }
  };

  const requestDelete = (memory) => {
    if (deletingKeys.has(memoryKey(memory))) return;
    setConfirmDelete({ show: true, memory });
  };

  const executeDelete = async () => {
    const memory = confirmDelete.memory;
    setConfirmDelete((prev) => ({ ...prev, show: false }));
    if (!memory) return;
    const key = memoryKey(memory);
    if (deletingKeys.has(key)) return;
    setDeletingKeys((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    try {
      const response = await api.delete(`memories/${encodeURIComponent(memory.type)}/${encodeURIComponent(memory.name)}`, {
        params: { agent_id: memory.agent_id || 'global' }
      });
      if (response.data.success) {
        setMemories((prev) => prev.filter((item) => memoryKey(item) !== key));
        if (selectedKey === key) setSelectedKey(null);
        if (editingKey === key) setEditingKey(null);
        await fetchMemories();
      }
    } catch (err) {
      setError(`Failed to delete memory: ${err.response?.data?.error || err.message}`);
    } finally {
      setDeletingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  const updateLink = (index, patch) => {
    setEditingMemory((prev) => ({
      ...prev,
      links: prev.links.map((link, linkIndex) => (linkIndex === index ? { ...link, ...patch } : link))
    }));
  };

  const clearFilters = () => {
    setSelectedAgents([]);
    setAgentMatch('available');
    setSelectedLinks([]);
    setLinkQuery('');
  };

  const selectAllLinks = () => {
    const visible = visibleLinkOptions.map((option) => option.value);
    setSelectedLinks((current) => [...new Set([...current, ...visible])]);
  };

  const selectNoLinks = () => {
    const visible = new Set(visibleLinkOptions.map((option) => option.value));
    setSelectedLinks((current) => current.filter((value) => !visible.has(value)));
  };

  const toggleIn = (current, value) => (
    current.includes(value) ? current.filter((item) => item !== value) : [...current, value]
  );

  const toggleAgent = (agentId) => {
    setAgentMatch('available');
    setSelectedAgents((current) => toggleIn(current, agentId));
  };

  const toggleLink = (value) => {
    setSelectedLinks((current) => toggleIn(current, value));
  };

  const applyOnlyAgent = (agentId, match) => {
    setTypeFilter('all');
    setQuery('');
    setSelectedAgents([agentId]);
    setAgentMatch(match);
    setSelectedLinks([]);
  };

  const applyOnlyLink = (link) => {
    setTypeFilter('all');
    setQuery('');
    setSelectedAgents([]);
    setAgentMatch('available');
    setSelectedLinks([linkFilterValue(link)]);
    setLinkQuery('');
  };

  const renderLinkFields = () => (
    <Form.Group className="mb-3">
      <Form.Label>Links</Form.Label>
      {(editingMemory.links || []).map((link, index) => (
        <div className="d-flex gap-2 mb-2" key={`${editingMemory.name}-link-${index}`}>
          <Form.Select
            value={link.kind}
            disabled={isSavingEdit}
            onChange={(e) => updateLink(index, { kind: e.target.value })}
            style={{ maxWidth: '10rem' }}
          >
            <option value="view">View</option>
            <option value="database">Database</option>
            <option value="tag">Tag</option>
          </Form.Select>
          <Form.Control
            type="text"
            placeholder={link.kind === 'view' ? 'sales.bv_orders' : 'Name'}
            value={link.name}
            disabled={isSavingEdit}
            onChange={(e) => updateLink(index, { name: e.target.value })}
          />
          <button
            type="button"
            className="rcc-icon-btn rcc-icon-btn-danger"
            disabled={isSavingEdit}
            title="Remove link"
            onClick={() => setEditingMemory((prev) => ({
              ...prev,
              links: prev.links.filter((_, linkIndex) => linkIndex !== index)
            }))}
          >
            <i className="bi bi-x-lg" />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="rcc-text-btn"
        disabled={isSavingEdit}
        onClick={() => setEditingMemory((prev) => ({ ...prev, links: [...(prev.links || []), emptyLink()] }))}
      >
        <i className="bi bi-plus-lg" />
        Add link
      </button>
    </Form.Group>
  );

  const renderDetail = () => {
    if (!selected) {
      return (
        <div className="rcc-split-detail-empty">
          <p className="text-muted mb-0">Select a memory to read it.</p>
        </div>
      );
    }
    const meta = TYPE_META[selected.type] || TYPE_META.user;
    const links = selected.links || [];
    return (
      <div className="rcc-split-detail-card">
        <span className={`rcc-badge rcc-split-type-badge mem-type-${selected.type}`}>
          <i className={`bi ${meta.icon}`} />
          {meta.label}
        </span>
        {isEditing ? (
          <Form.Group className="mb-3 mt-3">
            <Form.Label>Description</Form.Label>
            <Form.Control
              type="text"
              value={editingMemory.description}
              onChange={(e) => setEditingMemory((prev) => ({ ...prev, description: e.target.value }))}
              disabled={isSavingEdit}
              maxLength={MAX_DESCRIPTION_LENGTH}
            />
          </Form.Group>
        ) : (
          <h5 className="rcc-split-detail-title">{selected.description || selected.name}</h5>
        )}
        {isEditing ? (
          <>
            {isLinkedType(editingMemory.memoryType) && renderLinkFields()}
            <Form.Group className="mb-3">
              <Form.Label>Note</Form.Label>
              <Form.Control
                as="textarea"
                rows={8}
                value={editingMemory.body}
                onChange={(e) => setEditingMemory((prev) => ({ ...prev, body: e.target.value }))}
                disabled={isSavingEdit}
              />
            </Form.Group>
          </>
        ) : (
          <p className="rcc-split-detail-body">{(selected.body || '').trim()}</p>
        )}
        <dl className="rcc-split-facts">
          <div>
            <dt>Agents</dt>
            <dd className="mem-audience">
              {audienceIds(selected).map((id) => (
                <button
                  key={id}
                  type="button"
                  className="mem-tag"
                  title={`Show memories available to ${agentName(id)}`}
                  onClick={() => applyOnlyAgent(id, 'available')}
                >
                  {agentName(id)}
                </button>
              ))}
            </dd>
          </div>
          <div>
            <dt>Saved by</dt>
            <dd className="mem-audience">
              <button
                type="button"
                className="mem-tag"
                title={`Show memories saved by ${agentName(selected.agent_id)}`}
                onClick={() => applyOnlyAgent(selected.agent_id || 'global', 'owner')}
              >
                {agentName(selected.agent_id)}
              </button>
            </dd>
          </div>
          {links.length > 0 && (
            <div>
              <dt>Associated metadata</dt>
              <dd className="mem-link-pills">
                {[...links].sort(compareLinks).map((link, index) => (
                  <button
                    type="button"
                    className="mem-meta-link"
                    key={`${link.kind}-${link.name}-${index}`}
                    title={`Show memories linked to ${link.name}`}
                    onClick={() => applyOnlyLink(link)}
                  >
                    <span className="mem-meta-kind">{kindWord(link.kind)}</span>
                    <span className="mem-meta-name">{link.name}</span>
                  </button>
                ))}
              </dd>
            </div>
          )}
          {selected.modified && (
            <div>
              <dt>Updated</dt>
              <dd>{formatUpdated(selected.modified)}</dd>
            </div>
          )}
        </dl>
        <div className="rcc-split-actions">
          {isEditing ? (
            <>
              <button
                type="button"
                className="rcc-ghost-btn"
                onClick={() => { setEditingKey(null); setEditingMemory(emptyMemory); setError(null); }}
                disabled={isSavingEdit}
              >
                Cancel
              </button>
              <button type="button" className="rcc-primary-btn" onClick={handleSaveEdit} disabled={isSavingEdit}>
                {isSavingEdit ? (<><Spinner animation="border" size="sm" />Saving...</>) : 'Save'}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="rcc-text-btn" onClick={() => handleStartEdit(selected)}>
                <i className="bi bi-pencil" />
                Edit
              </button>
              <button
                type="button"
                className="rcc-text-btn rcc-text-btn-danger"
                onClick={() => requestDelete(selected)}
                disabled={deletingKeys.has(memoryKey(selected))}
              >
                {deletingKeys.has(memoryKey(selected))
                  ? <Spinner animation="border" size="sm" />
                  : <i className="bi bi-trash" />}
                Delete
              </button>
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <>
      <BaseModal
        show={show}
        onHide={handleClose}
        title="Memories"
        headerBadges={
          <span className="rcc-quota">
            {memories.length} {memories.length === 1 ? 'memory' : 'memories'}
          </span>
        }
        size="xl"
        fixedHeight
        backdrop="static"
        className="mem-modal"
      >
        <div className="rcc-split-shell">
          <div className="rcc-split-top">
            {error && (
              <div className="rcc-banner rcc-banner-danger" role="alert">
                <i className="bi bi-exclamation-triangle-fill" />
                <div>{error}</div>
                <button
                  type="button"
                  className="rcc-banner-close"
                  onClick={() => setError(null)}
                  aria-label="Dismiss error"
                >
                  <i className="bi bi-x" />
                </button>
              </div>
            )}

            {showInfoBanner && (
              <div className="rcc-banner rcc-banner-info">
                <i className="bi bi-info-circle-fill" />
                <div>
                  As you chat with agents, they will form memories about you, your workflows and your preferences. These memories will be stored and available across sessions. Each agent, the general chat and every specialized agent will have their own memories. There are three categories of memories:
                  <ul>
                    <li>
                      <strong>About you</strong>. A fact about you, your personal preferences or workflows, with no link to any view, database, or tag. For example, that you like to be called Jamie instead of James.
                    </li>
                    <li>
                      <strong>Data preferences</strong>. A personal preference about specific metadata, linked to at least one view, database, or tag (and it can be linked to several). For example, that you like the field salary in samples_bank.loan to always show the currency sign.
                    </li>
                    <li>
                      <strong>Data facts</strong>. An objective fact about views, databases, or tags that the metadata itself does not state, linked to at least one of them. For example, that the currency of salary in samples_bank.loan is USD.
                    </li>
                  </ul>
                  You can ask the agent to create or edit memories for you during a conversation, or let them autonomously form memories about you based on your interactions.
                </div>
                <button
                  type="button"
                  className="rcc-banner-close"
                  onClick={() => setShowInfoBanner(false)}
                  aria-label="Dismiss note"
                >
                  <i className="bi bi-x" />
                </button>
              </div>
            )}
          </div>

          <div className="rcc-tabs-bar">
            <ul className="nav nav-tabs rcc-report-tabs" role="tablist" aria-label="Memory type">
              {TYPE_FILTERS.map((option) => (
                <li className="nav-item" role="presentation" key={option.id}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={typeFilter === option.id}
                    className={`nav-link rcc-tab-link ${typeFilter === option.id ? 'active' : ''}`}
                    onClick={() => setTypeFilter(option.id)}
                  >
                    {option.label}
                    <span className="rcc-filter-count">{typeCounts[option.id]}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="rcc-toolbar-right">
              <div className="rcc-search">
                <i className="bi bi-search" />
                <input
                  type="search"
                  placeholder="Search memories"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search memories"
                />
              </div>
              <button
                type="button"
                ref={filterButtonRef}
                className={`rcc-text-btn mem-filter-btn ${filtersOpen || activeFilterCount ? 'is-active' : ''}`}
                onClick={(event) => {
                  event.stopPropagation();
                  setFiltersOpen((open) => !open);
                }}
                aria-expanded={filtersOpen}
              >
                <i className="bi bi-funnel" />
                Filters
                {activeFilterCount > 0 && <span className="rcc-filter-count">{activeFilterCount}</span>}
              </button>
              <Overlay
                show={filtersOpen}
                target={filterButtonRef.current}
                placement="bottom-end"
                container={() => document.querySelector('.mem-modal')}
                popperConfig={{ strategy: 'fixed' }}
              >
                {(overlayProps) => (
                  <Popover
                    {...overlayProps}
                    className="mem-filter-popover"
                    style={{ ...overlayProps.style, zIndex: 1400 }}
                  >
                    <Popover.Body onMouseDown={(event) => event.stopPropagation()}>
                      <Form.Group className="mb-2">
                        <Form.Label>Agents</Form.Label>
                        <FilterList
                          ariaLabel="Agents"
                          values={selectedAgents}
                          onToggle={toggleAgent}
                          options={chatbots.map((bot) => ({
                            value: agentIdOf(bot),
                            label: bot.name || agentName(agentIdOf(bot)),
                          }))}
                        />
                      </Form.Group>
                      <Form.Group className="mb-3">
                        <div className="mem-filter-label-row">
                          <Form.Label className="mb-0">Associated metadata</Form.Label>
                          <div className="mem-filter-quick">
                            <button type="button" onClick={selectAllLinks}>All</button>
                            <button type="button" onClick={selectNoLinks}>None</button>
                          </div>
                        </div>
                        <div className="mem-filter-search">
                          <i className="bi bi-search" />
                          <input
                            type="search"
                            placeholder="Search metadata"
                            value={linkQuery}
                            onChange={(e) => setLinkQuery(e.target.value)}
                            aria-label="Search associated metadata"
                          />
                        </div>
                        <FilterList
                          ariaLabel="Associated metadata"
                          values={selectedLinks}
                          onToggle={toggleLink}
                          emptyLabel={linkQuery.trim() ? 'No matching metadata' : 'No associated metadata'}
                          options={visibleLinkOptions}
                        />
                      </Form.Group>
                      <button type="button" className="rcc-text-btn" onClick={clearFilters}>
                        Clear filters
                      </button>
                    </Popover.Body>
                  </Popover>
                )}
              </Overlay>
            </div>
          </div>

          {isLoading && (
            <div className="rcc-split-loading">
              <Spinner animation="border" variant="secondary" />
            </div>
          )}

          {!isLoading && memories.length === 0 && (
            <div className="rcc-split-empty">
              <i className="bi bi-journal-text" />
              <p className="mb-1 fw-semibold">No memories yet</p>
              <p className="text-muted mb-0 small">The agent saves them when a fact should be useful on a later question.</p>
            </div>
          )}

          {!isLoading && memories.length > 0 && (
            <div className="rcc-split">
              <div className="rcc-split-list" role="listbox" aria-label="Memories">
                <div className="rcc-split-list-head">
                  <span>{filtered.length} {filtered.length === 1 ? 'memory' : 'memories'}</span>
                </div>
                {filtered.length === 0 && (
                  <p className="rcc-split-list-empty">No memories match these filters.</p>
                )}
                {filtered.map((memory) => {
                  const key = memoryKey(memory);
                  const meta = TYPE_META[memory.type] || TYPE_META.user;
                  const active = key === selectedKey;
                  return (
                    <button
                      type="button"
                      role="option"
                      aria-selected={active}
                      key={key}
                      className={`rcc-split-row ${active ? 'is-active' : ''}`}
                      onClick={() => selectMemory(memory)}
                    >
                      <span className={`rcc-split-row-icon mem-type-${memory.type}`}>
                        <i className={`bi ${meta.icon}`} />
                      </span>
                      <span className="rcc-split-row-text">
                        <span className="rcc-split-row-title">{memory.description || memory.name}</span>
                        <span className="rcc-split-row-sub">{meta.label}</span>
                      </span>
                      <i className="bi bi-chevron-right rcc-split-row-chevron" />
                    </button>
                  );
                })}
              </div>
              <div className="rcc-split-detail">
                {renderDetail()}
              </div>
            </div>
          )}
        </div>
      </BaseModal>

      <ConfirmationModal
        show={confirmDelete.show}
        onHide={() => setConfirmDelete({ show: false, memory: null })}
        onConfirm={executeDelete}
        nested
        title="Delete memory"
        message={`Are you sure you want to delete the memory "${confirmDelete.memory?.description || confirmDelete.memory?.name || ''}"? This action cannot be undone.`}
        confirmLabel="Yes, delete"
      />
    </>
  );
};

PersonalMemoriesModal.propTypes = {
  show: PropTypes.bool.isRequired,
  handleClose: PropTypes.func.isRequired,
  chatbots: PropTypes.array,
  selectedChatbot: PropTypes.object,
};

export default PersonalMemoriesModal;
