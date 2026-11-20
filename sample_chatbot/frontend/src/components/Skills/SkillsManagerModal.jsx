import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import PropTypes from 'prop-types';
import { BaseModal, ConfirmationModal } from '../Common/Modal';
import Spinner from 'react-bootstrap/Spinner';
import Form from 'react-bootstrap/Form';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';
import api from '../../api/client';
import NotificationToast from '../NotificationToast/NotificationToast';
import './SkillsManagerModal.css';

const emptyNewSkill = {
  skillName: '',
  description: '',
  content: ''
};

const emptyUpload = {
  skillName: '',
  fileName: '',
  content: ''
};

const MAX_SKILL_DESCRIPTION_LENGTH = 1024;
const SKILL_NAME_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;
const SKILL_NAME_RULES =
  'at most 64 characters, lowercase letters, numbers, and hyphens only, and must not start or end with a hyphen';

const OVERLAY_PROPS = { container: () => document.body, popperConfig: { strategy: 'fixed' } };

const SCOPE_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'system', label: 'System' },
  { id: 'personal', label: 'Personal' },
];

const skillDisplayMeta = (skill) => {
  if (skill.valid === false) {
    return { label: 'Error', icon: 'bi-exclamation-triangle-fill', badgeClass: 'rcc-badge-error' };
  }
  if (skill.scope === 'personal') {
    return { label: 'Personal', icon: 'bi-person', badgeClass: 'rcc-badge-personal' };
  }
  return { label: 'System', icon: 'bi-globe2', badgeClass: 'rcc-badge-system' };
};

const skillOrder = (skill) => (skill.valid === false ? 2 : skill.scope === 'personal' ? 1 : 0);

// Extract the description from a SKILL.md frontmatter block, if present.
const parseFrontmatter = (content) => {
  const text = content.trimStart();
  if (!text.startsWith('---')) return {};
  const end = text.indexOf('\n---', 3);
  if (end === -1) return {};
  const result = {};
  for (const line of text.slice(3, end).split('\n')) {
    const sep = line.indexOf(':');
    if (sep === -1) continue;
    const key = line.slice(0, sep).trim().toLowerCase();
    const value = line.slice(sep + 1).trim().replace(/^["']|["']$/g, '');
    if (key === 'name' || key === 'description') result[key] = value;
  }
  return result;
};

const sanitizeSuggestedSkillName = (raw) => (
  String(raw || '')
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
);

const SkillsManagerModal = ({ show, handleClose, hasActiveConversation = false, selectedChatbot }) => {
  const [skills, setSkills] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [scopeFilter, setScopeFilter] = useState('all');
  const [selectedSkillName, setSelectedSkillName] = useState(null);

  const [showAddModal, setShowAddModal] = useState(false);
  const [addMode, setAddMode] = useState('create');
  const [addError, setAddError] = useState(null);
  const [newSkill, setNewSkill] = useState(emptyNewSkill);
  const [upload, setUpload] = useState(emptyUpload);
  const [isAdding, setIsAdding] = useState(false);

  const [editingSkill, setEditingSkill] = useState(null);
  const [editingContent, setEditingContent] = useState('');
  const [isLoadingEditContent, setIsLoadingEditContent] = useState(false);
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  const [loadedSkillContent, setLoadedSkillContent] = useState({ skillName: null, content: '' });
  const [isLoadingContent, setIsLoadingContent] = useState(false);

  const [deletingSkills, setDeletingSkills] = useState(() => new Set());
  const [confirmDelete, setConfirmDelete] = useState({ show: false, skillName: '' });

  // Tracks whether the user has made any change during this open-session of
  // the modal. Used to decide whether to warn on close that changes won't
  // apply to an ongoing conversation.
  const [hasChanges, setHasChanges] = useState(false);

  const [showInfoBanner, setShowInfoBanner] = useState(true);
  const detailRef = useRef(null);
  const editRequestIdRef = useRef(0);

  const invalidateEditRequest = useCallback(() => {
    editRequestIdRef.current += 1;
    setIsLoadingEditContent(false);
  }, []);

  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: '',
    variant: 'info',
    title: '',
    duration: 8000,
  });

  const showToast = (message, variant, title, duration = 8000) => {
    setToastConfig({ show: true, message, variant, title, duration });
  };

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const notifySkillsChanged = useCallback(() => {
    setHasChanges(true);
  }, []);

  // Reset dirty/view state every time the modal is opened.
  useEffect(() => {
    if (show) {
      invalidateEditRequest();
      setError(null);
      setHasChanges(false);
      setQuery('');
      setScopeFilter('all');
      setSelectedSkillName(null);
      setLoadedSkillContent({ skillName: null, content: '' });
      setIsLoadingContent(false);
      setShowAddModal(false);
      setAddMode('create');
      setAddError(null);
      setNewSkill(emptyNewSkill);
      setUpload(emptyUpload);
      setEditingSkill(null);
      setEditingContent('');
      setShowInfoBanner(true);
    }
  }, [show, invalidateEditRequest]);

  const requestClose = () => {
    if (hasChanges && hasActiveConversation) {
      showToast(
        "Changes saved. The agent may rely on previous context and ignore skill changes. Start a new chat to make sure they apply.",
        "info",
        "Skills updated",
        8000
      );
    }
    handleClose();
  };

  const fetchSkills = useCallback(async () => {
    if (!show) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get('skills/list');
      if (response.data.success) {
        setSkills(response.data.skills || []);
      }
    } catch (err) {
      setError('Failed to load skills');
      console.error('Error fetching skills:', err);
    } finally {
      setIsLoading(false);
    }
  }, [show]);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  const scopeCounts = useMemo(() => ({
    all: skills.length,
    system: skills.filter((skill) => skill.scope !== 'personal').length,
    personal: skills.filter((skill) => skill.scope === 'personal').length,
  }), [skills]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...skills]
      .filter((skill) => {
        if (scopeFilter === 'system' && skill.scope === 'personal') return false;
        if (scopeFilter === 'personal' && skill.scope !== 'personal') return false;
        if (!needle) return true;
        const haystack = [skill.skill_name, skill.description, ...(skill.references || [])]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(needle);
      })
      .sort((left, right) => {
        const byOrder = skillOrder(left) - skillOrder(right);
        if (byOrder !== 0) return byOrder;
        return String(left.skill_name || '').localeCompare(String(right.skill_name || ''));
      });
  }, [skills, scopeFilter, query]);

  const filteredKey = filtered.map((skill) => skill.skill_name).join('|');

  useEffect(() => {
    if (!show || isLoading) return;
    setSelectedSkillName((current) => {
      if (!filtered.length) return null;
      if (current && filtered.some((skill) => skill.skill_name === current)) return current;
      return filtered[0].skill_name;
    });
  }, [show, isLoading, filteredKey]);

  useEffect(() => {
    if (editingSkill && editingSkill !== selectedSkillName) {
      setEditingSkill(null);
      setEditingContent('');
    }
  }, [editingSkill, selectedSkillName]);

  const selected = filtered.find((skill) => skill.skill_name === selectedSkillName) || null;
  const isEditing = Boolean(selected && editingSkill === selected.skill_name);
  const detailContent = loadedSkillContent.skillName === selected?.skill_name ? loadedSkillContent.content : '';

  useEffect(() => {
    if (!show || !selected || isEditing) {
      setIsLoadingContent(false);
      return undefined;
    }
    if (loadedSkillContent.skillName === selected.skill_name) {
      setIsLoadingContent(false);
      return undefined;
    }
    let cancelled = false;
    setIsLoadingContent(true);
    api.get(`skills/read/${encodeURIComponent(selected.skill_name)}`)
      .then((response) => {
        if (!cancelled && response.data.success) {
          setLoadedSkillContent({
            skillName: selected.skill_name,
            content: response.data.content || '',
          });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(`Failed to read skill: ${err.response?.data?.error || err.message}`);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingContent(false);
      });
    return () => { cancelled = true; };
  }, [show, selected?.skill_name, isEditing, loadedSkillContent.skillName]);

  useEffect(() => {
    if (detailRef.current) detailRef.current.scrollTop = 0;
  }, [selected?.skill_name, isEditing]);

  const selectSkill = (skill) => {
    invalidateEditRequest();
    setError(null);
    setShowAddModal(false);
    setAddError(null);
    setNewSkill(emptyNewSkill);
    setUpload(emptyUpload);
    if (skill.skill_name !== selectedSkillName) {
      setEditingSkill(null);
      setEditingContent('');
    }
    setSelectedSkillName(skill.skill_name);
  };

  const handleStartAdd = () => {
    setAddError(null);
    setNewSkill(emptyNewSkill);
    setUpload(emptyUpload);
    setAddMode('create');
    setShowAddModal(true);
  };

  const handleDelete = (skillName) => {
    if (deletingSkills.has(skillName)) return;
    setConfirmDelete({ show: true, skillName });
  };

  const executeDelete = async () => {
    const { skillName } = confirmDelete;
    setConfirmDelete((prev) => ({ ...prev, show: false }));
    if (!skillName || deletingSkills.has(skillName)) return;
    if (editingSkill === skillName) invalidateEditRequest();
    setDeletingSkills((prev) => {
      const next = new Set(prev);
      next.add(skillName);
      return next;
    });
    try {
      const response = await api.delete(`skills/delete/${encodeURIComponent(skillName)}`);
      if (response.data.success) {
        setSkills((prev) => prev.filter((s) => s.skill_name !== skillName));
        if (selectedSkillName === skillName) {
          setSelectedSkillName(null);
        }
        if (loadedSkillContent.skillName === skillName) {
          setLoadedSkillContent({ skillName: null, content: '' });
        }
        if (editingSkill === skillName) {
          invalidateEditRequest();
          setEditingSkill(null);
          setEditingContent('');
        }
        notifySkillsChanged();
      }
    } catch (err) {
      setError(`Failed to delete skill: ${err.response?.data?.error || err.message}`);
    } finally {
      setDeletingSkills((prev) => {
        const next = new Set(prev);
        next.delete(skillName);
        return next;
      });
    }
  };

  const validateSkillName = (skillName) => {
    if (!skillName) { setAddError('Please provide a skill name'); return false; }
    if (!SKILL_NAME_PATTERN.test(skillName)) {
      setAddError(`Skill names must be ${SKILL_NAME_RULES}`);
      return false;
    }
    return true;
  };

  const validateDescription = (description) => {
    const trimmed = (description || '').trim();
    if (!trimmed) { setAddError('Please provide a description'); return false; }
    if (trimmed.length > MAX_SKILL_DESCRIPTION_LENGTH) {
      setAddError(`Description must be at most ${MAX_SKILL_DESCRIPTION_LENGTH} characters`);
      return false;
    }
    return true;
  };

  const validateUploadedContent = (skillName, content) => {
    const frontmatter = parseFrontmatter(content);
    if (!frontmatter.name && !frontmatter.description) {
      setAddError('SKILL.md must start with a YAML frontmatter block declaring name and description');
      return false;
    }
    if (!frontmatter.name) {
      setAddError('Frontmatter must declare a non-empty name');
      return false;
    }
    if (!SKILL_NAME_PATTERN.test(frontmatter.name)) {
      setAddError(`Frontmatter name must be ${SKILL_NAME_RULES}`);
      return false;
    }
    if (frontmatter.name !== skillName) {
      setAddError(`Frontmatter name '${frontmatter.name}' must match the skill name '${skillName}'`);
      return false;
    }
    if (!validateDescription(frontmatter.description || '')) return false;
    return true;
  };

  const submitNewSkill = async (skillName, content) => {
    setIsAdding(true);
    setAddError(null);
    try {
      const response = await api.post('skills/create', {
        skill_name: skillName,
        content
      });
      if (response.data.success) {
        invalidateEditRequest();
        setEditingSkill(null);
        setEditingContent('');
        await fetchSkills();
        setScopeFilter('all');
        setQuery('');
        setLoadedSkillContent({ skillName, content });
        setSelectedSkillName(skillName);
        setNewSkill(emptyNewSkill);
        setUpload(emptyUpload);
        setShowAddModal(false);
        setAddError(null);
        notifySkillsChanged();
      }
    } catch (err) {
      setAddError(`Failed to create skill: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsAdding(false);
    }
  };

  const handleCreateSkill = async (e) => {
    e.preventDefault();
    const skillName = newSkill.skillName.trim();
    if (!validateSkillName(skillName)) return;
    if (!validateDescription(newSkill.description)) return;
    if (!newSkill.content.trim()) { setAddError('Skill content cannot be empty'); return; }

    // The frontmatter is generated from the name and description fields.
    const content = `---\nname: ${skillName}\ndescription: ${newSkill.description.trim()}\n---\n\n${newSkill.content}`;
    await submitNewSkill(skillName, content);
  };

  const handleUploadSkill = async (e) => {
    e.preventDefault();
    const skillName = upload.skillName.trim();
    if (!validateSkillName(skillName)) return;
    if (!upload.content.trim()) { setAddError('Please select a skill file to upload'); return; }
    if (!validateUploadedContent(skillName, upload.content)) return;
    await submitNewSkill(skillName, upload.content);
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!/\.(md|markdown|txt|yaml|yml)$/i.test(file.name)) {
      setAddError('Please select a markdown (.md), text (.txt) or YAML (.yaml) file');
      e.target.value = null;
      return;
    }
    setAddError(null);
    const reader = new FileReader();
    reader.onload = () => {
      const content = String(reader.result || '');
      const frontmatter = parseFrontmatter(content);
      const suggestedName = sanitizeSuggestedSkillName(
        frontmatter.name || file.name.replace(/\.(md|markdown|txt|yaml|yml)$/i, '')
      );
      setUpload((prev) => ({
        skillName: prev.skillName || (suggestedName === 'skill' ? '' : suggestedName),
        fileName: file.name,
        content
      }));
    };
    reader.readAsText(file);
  };

  const handleCancelAddForm = () => {
    if (isAdding) return;
    setShowAddModal(false);
    setNewSkill(emptyNewSkill);
    setUpload(emptyUpload);
    setAddError(null);
  };

  const handleStartEdit = async (skillName) => {
    const requestId = ++editRequestIdRef.current;
    setShowAddModal(false);
    setError(null);
    setSelectedSkillName(skillName);

    if (loadedSkillContent.skillName === skillName && !isLoadingContent) {
      setIsLoadingEditContent(false);
      setEditingSkill(skillName);
      setEditingContent(loadedSkillContent.content);
      return;
    }

    setEditingSkill(skillName);
    setEditingContent('');
    setIsLoadingEditContent(true);
    try {
      const response = await api.get(`skills/read/${encodeURIComponent(skillName)}`);
      if (editRequestIdRef.current !== requestId) return;
      if (response.data.success) {
        const content = response.data.content || '';
        setLoadedSkillContent({ skillName, content });
        setEditingContent(content);
      }
    } catch (err) {
      if (editRequestIdRef.current !== requestId) return;
      setError(`Failed to read skill: ${err.response?.data?.error || err.message}`);
      setEditingSkill(null);
    } finally {
      if (editRequestIdRef.current === requestId) {
        setIsLoadingEditContent(false);
      }
    }
  };

  const handleSaveEdit = async () => {
    if (!editingContent.trim()) { setError('Skill content cannot be empty'); return; }
    const targetSkill = editingSkill;
    const updatedContent = editingContent;
    setIsSavingEdit(true);
    setError(null);
    try {
      const response = await api.put(`skills/update/${encodeURIComponent(targetSkill)}`, { content: updatedContent });
      if (response.data.success) {
        await fetchSkills();
        setLoadedSkillContent({ skillName: targetSkill, content: updatedContent });
        setEditingSkill(null);
        setEditingContent('');
        notifySkillsChanged();
      }
    } catch (err) {
      setError(`Failed to update skill: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsSavingEdit(false);
    }
  };

  const renderAddForm = () => (
    <>
      {addError && (
        <div className="rcc-banner rcc-banner-danger" role="alert">
          <i className="bi bi-exclamation-triangle-fill" />
          <div>{addError}</div>
          <button
            type="button"
            className="rcc-banner-close"
            onClick={() => setAddError(null)}
            aria-label="Dismiss error"
          >
            <i className="bi bi-x" />
          </button>
        </div>
      )}

      <div className="skm-add-modes" role="tablist" aria-label="Add skill method">
        <button
          type="button"
          role="tab"
          aria-selected={addMode === 'create'}
          className={`skm-mode-btn ${addMode === 'create' ? 'is-active' : ''}`}
          onClick={() => { setAddError(null); setAddMode('create'); }}
          disabled={isAdding}
        >
          <i className="bi bi-pencil-square" />
          Create from scratch
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={addMode === 'upload'}
          className={`skm-mode-btn ${addMode === 'upload' ? 'is-active' : ''}`}
          onClick={() => { setAddError(null); setAddMode('upload'); }}
          disabled={isAdding}
        >
          <i className="bi bi-upload" />
          Upload a file
        </button>
      </div>

      {addMode === 'create' ? (
        <Form key="create" id="skm-create-skill-form" onSubmit={handleCreateSkill}>
          <Form.Group className="mb-3" controlId="skillName">
            <Form.Label>Skill name</Form.Label>
            <Form.Control
              type="text"
              placeholder="my-reporting-process"
              value={newSkill.skillName}
              onChange={(e) => setNewSkill((prev) => ({ ...prev, skillName: e.target.value }))}
              disabled={isAdding}
            />
            <Form.Text muted>
              Max 64 characters. Lowercase letters, numbers, and hyphens only. Must not start or end with a hyphen.
            </Form.Text>
          </Form.Group>
          <Form.Group className="mb-3" controlId="skillDescription">
            <Form.Label>Skill description</Form.Label>
            <Form.Control
              type="text"
              placeholder="What this skill does and when the agent should use it."
              value={newSkill.description}
              onChange={(e) => setNewSkill((prev) => ({ ...prev, description: e.target.value }))}
              disabled={isAdding}
              maxLength={MAX_SKILL_DESCRIPTION_LENGTH}
            />
            <Form.Text muted>Max {MAX_SKILL_DESCRIPTION_LENGTH} characters. Non-empty.</Form.Text>
          </Form.Group>
          <Form.Group className="mb-1" controlId="skillContent">
            <Form.Label>Contents</Form.Label>
            <Form.Control
              as="textarea"
              rows={5}
              className="skm-mono-textarea"
              placeholder="Step-by-step guidance for the agent..."
              value={newSkill.content}
              onChange={(e) => setNewSkill((prev) => ({ ...prev, content: e.target.value }))}
              disabled={isAdding}
            />
            <Form.Text muted>
              Just the guidance itself. The frontmatter (name and description) is generated for you.
            </Form.Text>
          </Form.Group>
        </Form>
      ) : (
        <Form key="upload" id="skm-upload-skill-form" onSubmit={handleUploadSkill}>
          <Form.Group className="mb-3" controlId="skillUploadFile">
            <Form.Label>Skill file (SKILL.md)</Form.Label>
            <Form.Control type="file" accept=".md,.markdown,.txt,.yaml,.yml" onChange={handleFileChange} disabled={isAdding} />
            <Form.Text muted>
              The SKILL.md file must come with a YAML frontmatter block declaring <code>name</code> and <code>description</code>.
            </Form.Text>
          </Form.Group>
          {upload.content && (
            <>
              <Form.Group className="mb-3" controlId="skillUploadName">
                <Form.Label>Skill name</Form.Label>
                <Form.Control
                  type="text"
                  value={upload.skillName}
                  onChange={(e) => setUpload((prev) => ({ ...prev, skillName: e.target.value }))}
                  disabled={isAdding}
                />
                <Form.Text muted>
                  Must match the frontmatter <code>name</code>. Max 64 characters.
                </Form.Text>
              </Form.Group>
              <Form.Group className="mb-1">
                <Form.Label>
                  Preview <span className="text-muted">({upload.fileName})</span>
                </Form.Label>
                <pre className="skm-view-pre">{upload.content}</pre>
              </Form.Group>
            </>
          )}
        </Form>
      )}
    </>
  );

  const renderDetail = () => {
    if (!selected) {
      return (
        <div className="rcc-split-detail-empty">
          <p className="text-muted mb-0">Select a skill to read it.</p>
        </div>
      );
    }

    const meta = skillDisplayMeta(selected);
    const badge = (
      <span className={`rcc-badge rcc-split-type-badge ${meta.badgeClass}`}>
        <i className={`bi ${meta.icon}`} />
        {meta.label}
      </span>
    );

    return (
      <div className="rcc-split-detail-card">
        {selected.valid === false ? (
          <OverlayTrigger
            placement="top"
            overlay={<Tooltip id={`skill-error-${selected.skill_name}`}>{selected.error || 'Invalid skill'}</Tooltip>}
            {...OVERLAY_PROPS}
          >
            {badge}
          </OverlayTrigger>
        ) : badge}

        <h5 className="rcc-split-detail-title skm-detail-title">{selected.skill_name}</h5>

        {isEditing ? (
          <>
            {isLoadingEditContent ? (
              <div className="text-center p-4">
                <Spinner animation="border" size="sm" variant="secondary" />
              </div>
            ) : (
              <Form.Group className="mb-3 mt-3">
                <Form.Label>Contents (SKILL.md)</Form.Label>
                <Form.Control
                  as="textarea"
                  rows={7}
                  className="skm-mono-textarea"
                  value={editingContent}
                  onChange={(e) => setEditingContent(e.target.value)}
                  disabled={isSavingEdit}
                />
              </Form.Group>
            )}
            <div className="rcc-split-actions">
              <button
                type="button"
                className="rcc-ghost-btn"
                onClick={() => {
                  invalidateEditRequest();
                  setEditingSkill(null);
                  setEditingContent('');
                  setError(null);
                }}
                disabled={isSavingEdit}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rcc-primary-btn"
                onClick={handleSaveEdit}
                disabled={isSavingEdit || isLoadingEditContent}
              >
                {isSavingEdit ? (<><Spinner animation="border" size="sm" />Saving...</>) : 'Save'}
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="rcc-split-detail-body">
              {selected.description || <em className="text-muted">No description</em>}
            </p>

            {selected.valid === false && selected.error && (
              <div className="rcc-banner rcc-banner-danger mb-3" role="alert">
                <i className="bi bi-exclamation-triangle-fill" />
                <div>{selected.error}</div>
              </div>
            )}

            {selected.references && selected.references.length > 0 && (
              <dl className="rcc-split-facts">
                <div>
                  <dt>References</dt>
                  <dd className="skm-ref-list">
                    {selected.references.map((ref) => (
                      <span key={ref} className="skm-code-badge">{ref}</span>
                    ))}
                  </dd>
                </div>
              </dl>
            )}

            <div className="skm-content-section">
              <div className="skm-content-label">Contents</div>
              {isLoadingContent ? (
                <div className="text-center p-4">
                  <Spinner animation="border" size="sm" variant="secondary" />
                </div>
              ) : (
                <pre className="skm-view-pre">{detailContent}</pre>
              )}
            </div>

            {selected.scope === 'personal' && (
              <div className="rcc-split-actions">
                <button type="button" className="rcc-text-btn" onClick={() => handleStartEdit(selected.skill_name)}>
                  <i className="bi bi-pencil" />
                  Edit
                </button>
                <button
                  type="button"
                  className="rcc-text-btn rcc-text-btn-danger"
                  onClick={() => handleDelete(selected.skill_name)}
                  disabled={deletingSkills.has(selected.skill_name)}
                >
                  {deletingSkills.has(selected.skill_name)
                    ? <Spinner animation="border" size="sm" />
                    : <i className="bi bi-trash" />}
                  Delete
                </button>
              </div>
            )}
          </>
        )}
      </div>
    );
  };

  return (
    <>
      <BaseModal
        show={show}
        onHide={requestClose}
        title="Skills Manager"
        headerBadges={
          <span className="rcc-quota">
            {skills.length} {skills.length === 1 ? 'skill' : 'skills'}
          </span>
        }
        size="xl"
        fixedHeight
        backdrop="static"
        className="skm-modal"
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
                  Skills are reusable procedures the agent can read on demand. There are two categories:
                  <ul>
                    <li>
                      <strong>System</strong>: Available to all users. Stored in the local filesystem under the <code>skills/</code> directory.
                    </li>
                    <li>
                      <strong>Personal</strong>: Only viewable and manageable by you. Stored in the associated chatbot database.
                    </li>
                  </ul>
                  You can activate or deactivate skills per agent in <strong>Administration</strong>.
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
            <ul className="nav nav-tabs rcc-report-tabs" role="tablist" aria-label="Skill category">
              {SCOPE_FILTERS.map((option) => (
                <li className="nav-item" role="presentation" key={option.id}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={scopeFilter === option.id}
                    className={`nav-link rcc-tab-link ${scopeFilter === option.id ? 'active' : ''}`}
                    onClick={() => setScopeFilter(option.id)}
                  >
                    {option.label}
                    <span className="rcc-filter-count">{scopeCounts[option.id]}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="rcc-toolbar-right">
              <div className="rcc-search">
                <i className="bi bi-search" />
                <input
                  type="search"
                  placeholder="Search skills"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search skills"
                />
              </div>
              <button
                type="button"
                className="rcc-primary-btn skm-add-btn"
                onClick={handleStartAdd}
              >
                <i className="bi bi-plus-lg" />
                Add Personal Skill
              </button>
            </div>
          </div>

          {isLoading && (
            <div className="rcc-split-loading">
              <Spinner animation="border" variant="secondary" />
            </div>
          )}

          {!isLoading && skills.length === 0 && (
            <div className="rcc-split-empty">
              <i className="bi bi-puzzle" />
              <p className="mb-1 fw-semibold">No skills available</p>
              <p className="text-muted mb-0 small">Click "Add Personal Skill" to create your first reusable procedure.</p>
            </div>
          )}

          {!isLoading && skills.length > 0 && (
            <div className="rcc-split">
              <div className="rcc-split-list" role="listbox" aria-label="Skills">
                <div className="rcc-split-list-head">
                  <span>{filtered.length} {filtered.length === 1 ? 'skill' : 'skills'}</span>
                </div>
                {filtered.length === 0 && (
                  <p className="rcc-split-list-empty">No skills match the current filter.</p>
                )}
                {filtered.map((skill) => {
                  const meta = skillDisplayMeta(skill);
                  const active = skill.skill_name === selectedSkillName;
                  return (
                    <button
                      type="button"
                      role="option"
                      aria-selected={active}
                      key={skill.skill_name}
                      className={`rcc-split-row ${active ? 'is-active' : ''}`}
                      onClick={() => selectSkill(skill)}
                    >
                      <span className={`rcc-split-row-icon ${meta.badgeClass}`}>
                        <i className={`bi ${meta.icon}`} />
                      </span>
                      <span className="rcc-split-row-text">
                        <span className="rcc-split-row-title skm-row-name">{skill.skill_name}</span>
                        <span className="rcc-split-row-sub">{meta.label}</span>
                      </span>
                      <i className="bi bi-chevron-right rcc-split-row-chevron" />
                    </button>
                  );
                })}
              </div>
              <div className="rcc-split-detail" ref={detailRef}>
                {renderDetail()}
              </div>
            </div>
          )}
        </div>
      </BaseModal>

      <BaseModal
        show={showAddModal}
        onHide={handleCancelAddForm}
        title="Add Personal Skill"
        size="md"
        nested
        scrollableBody
        backdrop="static"
        className="skm-add-modal"
        footer={
          <>
            <button
              type="button"
              className="rcc-ghost-btn"
              onClick={handleCancelAddForm}
              disabled={isAdding}
            >
              Cancel
            </button>
            <button
              type="submit"
              form={addMode === 'create' ? 'skm-create-skill-form' : 'skm-upload-skill-form'}
              className="rcc-primary-btn"
              disabled={isAdding || (addMode === 'upload' && !upload.content)}
            >
              {isAdding
                ? (<><Spinner animation="border" size="sm" />{addMode === 'upload' ? 'Uploading...' : 'Adding...'}</>)
                : (addMode === 'upload' ? 'Upload Skill' : 'Add Skill')}
            </button>
          </>
        }
      >
        {renderAddForm()}
      </BaseModal>

      <ConfirmationModal
        show={confirmDelete.show}
        onHide={() => setConfirmDelete((prev) => ({ ...prev, show: false }))}
        onConfirm={executeDelete}
        nested
        title="Delete Personal Skill"
        message={`Are you sure you want to delete your personal skill "${confirmDelete.skillName}"? This action cannot be undone.`}
        confirmLabel="Yes, delete"
      />

      <NotificationToast
        show={toastConfig.show}
        message={toastConfig.message}
        variant={toastConfig.variant}
        title={toastConfig.title}
        duration={toastConfig.duration}
        onClose={handleToastClose}
      />
    </>
  );
};

SkillsManagerModal.propTypes = {
  show: PropTypes.bool.isRequired,
  handleClose: PropTypes.func.isRequired,
  hasActiveConversation: PropTypes.bool,
  selectedChatbot: PropTypes.object
};

export default SkillsManagerModal;
