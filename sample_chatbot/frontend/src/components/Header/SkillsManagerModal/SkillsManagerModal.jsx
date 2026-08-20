import React, { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Table from 'react-bootstrap/Table';
import Form from 'react-bootstrap/Form';
import Badge from 'react-bootstrap/Badge';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';
import api from '../../../api/client';
import NotificationToast from '../../NotificationToast/NotificationToast';

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
  // addMode: null (closed) | 'choose' | 'create' | 'upload'
  const [addMode, setAddMode] = useState(null);
  const [newSkill, setNewSkill] = useState(emptyNewSkill);
  const [upload, setUpload] = useState(emptyUpload);
  const [isAdding, setIsAdding] = useState(false);
  const [editingSkill, setEditingSkill] = useState(null);
  const [editingContent, setEditingContent] = useState('');
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [viewingSkill, setViewingSkill] = useState(null);
  const [viewingContent, setViewingContent] = useState('');
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [deletingSkills, setDeletingSkills] = useState(() => new Set());

  // Tracks whether the user has made any change during this open-session of
  // the modal. Used to decide whether to warn on close that changes won't
  // apply to an ongoing conversation.
  const [hasChanges, setHasChanges] = useState(false);

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
      setHasChanges(false);
      setViewingSkill(null);
      setViewingContent('');
      setAddMode(null);
      setNewSkill(emptyNewSkill);
      setUpload(emptyUpload);
      setEditingSkill(null);
      setEditingContent('');
    }
  }, [show]);

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

  const handleView = async (skillName) => {
    if (viewingSkill === skillName) {
      setViewingSkill(null);
      setViewingContent('');
      return;
    }
    setViewingSkill(skillName);
    setViewingContent('');
    setIsLoadingContent(true);
    try {
      const response = await api.get(`skills/read/${skillName}`);
      if (response.data.success) {
        setViewingContent(response.data.content || '');
      }
    } catch (err) {
      setError(`Failed to read skill: ${err.response?.data?.error || err.message}`);
      setViewingSkill(null);
    } finally {
      setIsLoadingContent(false);
    }
  };

  const handleDelete = async (skillName) => {
    if (deletingSkills.has(skillName)) return;
    if (!window.confirm(`Are you sure you want to delete your personal skill "${skillName}"?`)) return;
    setDeletingSkills((prev) => {
      const next = new Set(prev);
      next.add(skillName);
      return next;
    });
    try {
      const response = await api.delete(`skills/delete/${skillName}`);
      if (response.data.success) {
        setSkills((prev) => prev.filter((s) => s.skill_name !== skillName));
        if (viewingSkill === skillName) {
          setViewingSkill(null);
          setViewingContent('');
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
    if (!skillName) { setError('Please provide a skill name'); return false; }
    if (!SKILL_NAME_PATTERN.test(skillName)) {
      setError(`Skill names must be ${SKILL_NAME_RULES}`);
      return false;
    }
    return true;
  };

  const validateDescription = (description) => {
    const trimmed = (description || '').trim();
    if (!trimmed) { setError('Please provide a description'); return false; }
    if (trimmed.length > MAX_SKILL_DESCRIPTION_LENGTH) {
      setError(`Description must be at most ${MAX_SKILL_DESCRIPTION_LENGTH} characters`);
      return false;
    }
    return true;
  };

  const validateUploadedContent = (skillName, content) => {
    const frontmatter = parseFrontmatter(content);
    if (!frontmatter.name && !frontmatter.description) {
      setError('SKILL.md must start with a YAML frontmatter block declaring name and description');
      return false;
    }
    if (!frontmatter.name) {
      setError('Frontmatter must declare a non-empty name');
      return false;
    }
    if (!SKILL_NAME_PATTERN.test(frontmatter.name)) {
      setError(`Frontmatter name must be ${SKILL_NAME_RULES}`);
      return false;
    }
    if (frontmatter.name !== skillName) {
      setError(`Frontmatter name '${frontmatter.name}' must match the skill name '${skillName}'`);
      return false;
    }
    if (!validateDescription(frontmatter.description || '')) return false;
    return true;
  };

  const submitNewSkill = async (skillName, content) => {
    setIsAdding(true);
    setError(null);
    try {
      const response = await api.post('skills/create', {
        skill_name: skillName,
        content
      });
      if (response.data.success) {
        await fetchSkills();
        setNewSkill(emptyNewSkill);
        setUpload(emptyUpload);
        setAddMode(null);
        notifySkillsChanged();
      }
    } catch (err) {
      setError(`Failed to create skill: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsAdding(false);
    }
  };

  const handleCreateSkill = async (e) => {
    e.preventDefault();
    const skillName = newSkill.skillName.trim();
    if (!validateSkillName(skillName)) return;
    if (!validateDescription(newSkill.description)) return;
    if (!newSkill.content.trim()) { setError('Skill content cannot be empty'); return; }

    // The frontmatter is generated from the name and description fields.
    const content = `---\nname: ${skillName}\ndescription: ${newSkill.description.trim()}\n---\n\n${newSkill.content}`;
    await submitNewSkill(skillName, content);
  };

  const handleUploadSkill = async (e) => {
    e.preventDefault();
    const skillName = upload.skillName.trim();
    if (!validateSkillName(skillName)) return;
    if (!upload.content.trim()) { setError('Please select a skill file to upload'); return; }
    if (!validateUploadedContent(skillName, upload.content)) return;
    await submitNewSkill(skillName, upload.content);
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!/\.(md|markdown|txt|yaml|yml)$/i.test(file.name)) {
      setError('Please select a markdown (.md), text (.txt) or YAML (.yaml) file');
      e.target.value = null;
      return;
    }
    setError(null);
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
    setAddMode(null);
    setNewSkill(emptyNewSkill);
    setUpload(emptyUpload);
  };

  const handleStartEdit = async (skillName) => {
    setEditingSkill(skillName);
    setEditingContent('');
    setViewingSkill(null);
    setViewingContent('');
    try {
      const response = await api.get(`skills/read/${skillName}`);
      if (response.data.success) {
        setEditingContent(response.data.content || '');
      }
    } catch (err) {
      setError(`Failed to read skill: ${err.response?.data?.error || err.message}`);
      setEditingSkill(null);
    }
  };

  const handleSaveEdit = async () => {
    if (!editingContent.trim()) { setError('Skill content cannot be empty'); return; }
    setIsSavingEdit(true);
    setError(null);
    try {
      const response = await api.put(`skills/update/${editingSkill}`, { content: editingContent });
      if (response.data.success) {
        setEditingSkill(null);
        setEditingContent('');
        await fetchSkills();
        notifySkillsChanged();
      }
    } catch (err) {
      setError(`Failed to update skill: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsSavingEdit(false);
    }
  };

  return (
    <>
      <Modal show={show} onHide={requestClose} centered size="xl" dialogClassName="modal-90w">
        <Modal.Header closeButton data-bs-theme="light">
          <Modal.Title>Skills Manager</Modal.Title>
        </Modal.Header>
        <Modal.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          {error && (
            <Alert variant="danger" onClose={() => setError(null)} dismissible>
              {error}
            </Alert>
          )}

          <Alert variant="primary" className="mb-3 py-2">
            <small>
              <i className="bi bi-info-circle me-1" />
              Skills are reusable procedures the agent can read on demand. There are two categories of skills:
              <ul className="mb-1 mt-1 ps-3">
                <li>
                  <strong>System</strong>. These skills are available to all users in the chatbot. System skills
                  consist of an SKILL.md file and optional references. Stored in the local filesystem under the skills/ directory.
                </li>
                <li>
                  <strong>Personal</strong>. These skills are only viewable by you. Personal skills consist only
                  of a SKILL.md, no skill references. Stored in the associated chatbot database.
                </li>
              </ul>
              You can activate or deactivate skills per chat/specialized agent, by opening those agent's
              settings under <strong>Administration</strong>.
            </small>
          </Alert>

          {addMode === null && (
            <Button
              variant="outline-dark"
              size="sm"
              className="mb-3"
              onClick={() => setAddMode('choose')}
            >
              + Add Personal Skill
            </Button>
          )}

          {addMode === 'choose' && (
            <div className="border rounded p-3 mb-3 bg-light">
              <h6 className="mb-3">Add Personal Skill</h6>
              <p className="text-muted mb-3"><small>How do you want to add your skill?</small></p>
              <div className="d-flex gap-2">
                <Button variant="dark" size="sm" onClick={() => setAddMode('create')}>
                  <i className="bi bi-pencil-square me-1" />Create from scratch
                </Button>
                <Button variant="dark" size="sm" onClick={() => setAddMode('upload')}>
                  <i className="bi bi-upload me-1" />Upload a file
                </Button>
                <Button variant="outline-secondary" size="sm" onClick={handleCancelAddForm}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {addMode === 'create' && (
            <Form onSubmit={handleCreateSkill} className="border rounded p-3 mb-3 bg-light">
              <h6 className="mb-3">Create Personal Skill</h6>
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
              <Form.Group className="mb-3" controlId="skillContent">
                <Form.Label>Contents</Form.Label>
                <Form.Control
                  as="textarea"
                  rows={10}
                  placeholder="Step-by-step guidance for the agent..."
                  value={newSkill.content}
                  onChange={(e) => setNewSkill((prev) => ({ ...prev, content: e.target.value }))}
                  disabled={isAdding}
                  style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                />
                <Form.Text muted>
                  Just the guidance itself — the frontmatter (name and description) is generated for you.
                </Form.Text>
              </Form.Group>
              <div className="d-flex gap-2">
                <Button variant="dark" size="sm" type="submit" disabled={isAdding}>
                  {isAdding ? (<><Spinner animation="border" size="sm" className="me-1" />Adding...</>) : 'Add Skill'}
                </Button>
                <Button variant="outline-secondary" size="sm" onClick={handleCancelAddForm} disabled={isAdding}>
                  Cancel
                </Button>
              </div>
            </Form>
          )}

          {addMode === 'upload' && (
            <Form onSubmit={handleUploadSkill} className="border rounded p-3 mb-3 bg-light">
              <h6 className="mb-3">Upload Personal Skill</h6>
              <Form.Group className="mb-3" controlId="skillUploadFile">
                <Form.Label>Skill file (SKILL.md)</Form.Label>
                <Form.Control type="file" accept=".md,.markdown,.txt,.yaml,.yml" onChange={handleFileChange} disabled={isAdding} />
                <Form.Text muted>
                  The SKILL.md file must come with a YAML frontmatter block of:
                  <ul className="mb-0 mt-1 ps-3">
                    <li>
                      <code>name</code>. Max 64 characters. Lowercase letters, numbers, and hyphens only.
                      Must not start or end with a hyphen.
                    </li>
                    <li>
                      <code>description</code>. Max 1024 characters. Non-empty. Describes what the skill
                      does and when to use it.
                    </li>
                  </ul>
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
                      Must match the frontmatter <code>name</code>. Max 64 characters. Lowercase letters,
                      numbers, and hyphens only. Must not start or end with a hyphen.
                    </Form.Text>
                  </Form.Group>
                  {upload.content && (() => {
                    const frontmatter = parseFrontmatter(upload.content);
                    const issues = [];
                    if (!frontmatter.name) issues.push('Missing frontmatter name');
                    else if (!SKILL_NAME_PATTERN.test(frontmatter.name)) issues.push('Frontmatter name is invalid');
                    else if (upload.skillName.trim() && frontmatter.name !== upload.skillName.trim()) {
                      issues.push(`Frontmatter name '${frontmatter.name}' does not match skill name`);
                    }
                    if (!frontmatter.description) issues.push('Missing frontmatter description');
                    else if (frontmatter.description.length > MAX_SKILL_DESCRIPTION_LENGTH) {
                      issues.push(`Description exceeds ${MAX_SKILL_DESCRIPTION_LENGTH} characters`);
                    }
                    if (issues.length === 0) return null;
                    return (
                      <Alert variant="warning" className="py-2">
                        <small>
                          <i className="bi bi-exclamation-triangle me-1" />
                          {issues.join('. ')}.
                        </small>
                      </Alert>
                    );
                  })()}
                  <Form.Group className="mb-3">
                    <Form.Label>Preview <span className="text-muted">({upload.fileName})</span></Form.Label>
                    <pre
                      className="border rounded p-2 bg-white"
                      style={{ whiteSpace: 'pre-wrap', fontSize: '0.8rem', maxHeight: '220px', overflowY: 'auto' }}
                    >
                      {upload.content}
                    </pre>
                  </Form.Group>
                </>
              )}
              <div className="d-flex gap-2">
                <Button variant="dark" size="sm" type="submit" disabled={isAdding || !upload.content}>
                  {isAdding ? (<><Spinner animation="border" size="sm" className="me-1" />Uploading...</>) : 'Upload Skill'}
                </Button>
                <Button variant="outline-secondary" size="sm" onClick={handleCancelAddForm} disabled={isAdding}>
                  Cancel
                </Button>
              </div>
            </Form>
          )}

          {isLoading && addMode === null && (
            <div className="text-center p-4"><Spinner animation="border" /></div>
          )}

          {!isLoading && skills.length === 0 && (
            <Alert variant="warning">
              No skills available. Click "Add Personal Skill" to create one.
            </Alert>
          )}

          {!isLoading && skills.length > 0 && (
            <Table striped bordered hover size="sm" variant="light">
              <thead>
                <tr>
                  <th style={{ width: '220px' }}>Name</th>
                  <th style={{ width: '100px' }}>Type</th>
                  <th>Description</th>
                  <th style={{ width: '160px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {skills.map((skill) => (
                  <React.Fragment key={skill.skill_name}>
                    <tr>
                      <td className="align-middle"><code>{skill.skill_name}</code></td>
                      <td className="align-middle">
                        {skill.valid === false ? (
                          <OverlayTrigger
                            placement="top"
                            overlay={(
                              <Tooltip id={`skill-error-${skill.skill_name}`}>
                                {skill.error || 'Invalid skill'}
                              </Tooltip>
                            )}
                          >
                            <Badge bg="danger" style={{ cursor: 'help' }}>Error</Badge>
                          </OverlayTrigger>
                        ) : skill.scope === 'personal' ? (
                          <Badge bg="dark"><i className="bi bi-person-fill me-1" />Personal</Badge>
                        ) : (
                          <Badge bg="success"><i className="bi bi-globe2 me-1" />System</Badge>
                        )}
                      </td>
                      <td className="align-middle">
                        <small>{skill.description || <em className="text-muted">No description</em>}</small>
                        {skill.references && skill.references.length > 0 && (
                          <div>
                            <small className="text-muted">References: {skill.references.join(', ')}</small>
                          </div>
                        )}
                      </td>
                      <td className="align-middle">
                        <div className="d-flex gap-2">
                          <Button
                            variant="outline-secondary"
                            size="sm"
                            onClick={() => handleView(skill.skill_name)}
                            title="View skill content"
                          >
                            <i className={`bi ${viewingSkill === skill.skill_name ? 'bi-eye-slash' : 'bi-eye'}`} />
                          </Button>
                          {skill.scope === 'personal' && (
                            <Button
                              variant="outline-secondary"
                              size="sm"
                              onClick={() => handleStartEdit(skill.skill_name)}
                              title="Edit personal skill"
                            >
                              <i className="bi bi-pencil" />
                            </Button>
                          )}
                          {skill.scope === 'personal' && (
                            <Button
                              variant="outline-danger"
                              size="sm"
                              onClick={() => handleDelete(skill.skill_name)}
                              disabled={deletingSkills.has(skill.skill_name)}
                              title="Delete personal skill"
                            >
                              {deletingSkills.has(skill.skill_name)
                                ? <Spinner animation="border" size="sm" />
                                : <i className="bi bi-trash" />}
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {editingSkill === skill.skill_name && (
                      <tr>
                        <td colSpan={4} className="bg-light">
                          <Form.Group className="mb-2">
                            <Form.Label className="fw-semibold"><small>Editing {skill.skill_name}</small></Form.Label>
                            <Form.Control
                              as="textarea"
                              rows={10}
                              value={editingContent}
                              onChange={(e) => setEditingContent(e.target.value)}
                              disabled={isSavingEdit}
                              style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                            />
                          </Form.Group>
                          <div className="d-flex gap-2">
                            <Button variant="dark" size="sm" onClick={handleSaveEdit} disabled={isSavingEdit}>
                              {isSavingEdit ? (<><Spinner animation="border" size="sm" className="me-1" />Saving...</>) : 'Save'}
                            </Button>
                            <Button
                              variant="outline-secondary"
                              size="sm"
                              onClick={() => { setEditingSkill(null); setEditingContent(''); }}
                              disabled={isSavingEdit}
                            >
                              Cancel
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )}
                    {viewingSkill === skill.skill_name && (
                      <tr>
                        <td colSpan={4} className="bg-light">
                          {isLoadingContent ? (
                            <div className="text-center p-3"><Spinner animation="border" size="sm" /></div>
                          ) : (
                            <pre
                              className="mb-0 p-2"
                              style={{ whiteSpace: 'pre-wrap', fontSize: '0.8rem', maxHeight: '300px', overflowY: 'auto' }}
                            >
                              {viewingContent}
                            </pre>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </Table>
          )}

          <Alert variant="info" className="mb-3 py-2">
            <small>
              <strong>Note:</strong> System skills are provided by your administrator in the AI SDK <code>skills/</code> folder.
              You can ask the chatbot to create or edit personal skills for you during a conversation.
            </small>
          </Alert>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="light" onClick={requestClose}>Close</Button>
        </Modal.Footer>
      </Modal>

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
