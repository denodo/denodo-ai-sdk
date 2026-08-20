import React, { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Table from 'react-bootstrap/Table';
import api from '../../../api/client';
import AddCSVForm from './AddCSVForm';
import SourceRow from './SourceRow';
import ScannedFileRow from './ScannedFileRow';
import NotificationToast from '../../NotificationToast/NotificationToast';

const emptyNewCSV = {
  file: null,
  description: '',
  delimiter: ';',
  path: null,
  sourceName: null,
  vectorizedColumns: [],
  private: false
};

const CSVManagerModal = ({ show, handleClose, hasActiveConversation = false, selectedChatbot }) => {
  const [sources, setSources] = useState([]);
  const [scannedFiles, setScannedFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCSV, setNewCSV] = useState(emptyNewCSV);
  const [isAdding, setIsAdding] = useState(false);
  const [preview, setPreview] = useState(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isGeneratingDescription, setIsGeneratingDescription] = useState(false);
  const [editingSource, setEditingSource] = useState(null);
  const [editingDescription, setEditingDescription] = useState('');
  const [currentUsername, setCurrentUsername] = useState('');
  const [currentUserIsAdmin, setCurrentUserIsAdmin] = useState(false);
  const [downloadingSources, setDownloadingSources] = useState(() => new Set());
  const [deletingSources, setDeletingSources] = useState(() => new Set());
  const [togglingPrivateSources, setTogglingPrivateSources] = useState(() => new Set());
  
  // Tracks whether the user has made any change to sources during this
  // open-session of the modal. Used to decide whether to warn on close
  // that changes won't apply to an ongoing conversation.
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

  // Flip the dirty flag whenever a mutation succeeds, so we know on close
  // whether to warn that changes won't apply to the ongoing conversation.
  const notifySourcesChanged = useCallback(() => {
    setHasChanges(true);
  }, []);

  // Reset dirty state every time the modal is opened.
  useEffect(() => {
    if (show) {
      setHasChanges(false);
    }
  }, [show]);

  // Intercept the Close button / backdrop dismiss: if the user made changes
  // and there's an ongoing conversation, show the warning via Toast.
  const requestClose = () => {
    if (hasChanges && hasActiveConversation) {
      showToast(
        "Changes saved. The agent may rely on previous context and ignore new files. Ask it to 'search again' or start a new chat.",
        "info",
        "Knowledge base updated",
        8000
      );
    }
    handleClose();
  };

  const addBusy = (setter, name) =>
    setter((prev) => {
      const next = new Set(prev);
      next.add(name);
      return next;
    });
  const removeBusy = (setter, name) =>
    setter((prev) => {
      const next = new Set(prev);
      next.delete(name);
      return next;
    });

  useEffect(() => {
    setCurrentUsername(localStorage.getItem('current_user') || '');
  }, [show]);

  const fetchSources = useCallback(async () => {
    if (!show) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get('csv/list');
      if (response.data.success) {
        setSources(response.data.sources || []);
        setCurrentUserIsAdmin(!!response.data.current_user_is_admin);
      }
    } catch (err) {
      setError('Failed to load CSV sources');
      console.error('Error fetching CSV sources:', err);
    } finally {
      setIsLoading(false);
    }
  }, [show]);

  const fetchScannedFiles = useCallback(async () => {
    if (!show) return;
    try {
      const response = await api.get('csv/scan');
      if (response.data.success) {
        const sourceNames = new Set(sources.map((s) => s.source_name));
        setScannedFiles((response.data.files || []).filter((f) => !sourceNames.has(f.source_name)));
      }
    } catch (err) {
      console.error('Error scanning CSV files:', err);
    }
  }, [show, sources]);

  useEffect(() => { fetchSources(); }, [fetchSources]);
  useEffect(() => { fetchScannedFiles(); }, [fetchScannedFiles]);

  const handleDelete = async (sourceName, deleteFile = false) => {
    if (deletingSources.has(sourceName)) return;
    const confirmMessage = `Are you sure you want to delete "${sourceName}"? This removes it for all users of this chatbot.${deleteFile ? ' The CSV file will also be deleted.' : ''}`;
    if (!window.confirm(confirmMessage)) return;
    addBusy(setDeletingSources, sourceName);
    try {
      const response = await api.delete(`csv/delete/${sourceName}`, { data: { delete_file: deleteFile } });
      if (response.data.success) {
        setSources((prev) => prev.filter((s) => s.source_name !== sourceName));
        notifySourcesChanged();
      }
    } catch (err) {
      setError(`Failed to delete source: ${err.response?.data?.error || err.message}`);
    } finally {
      removeBusy(setDeletingSources, sourceName);
    }
  };

  const handleTogglePrivate = async (sourceName, nextPrivate) => {
    if (togglingPrivateSources.has(sourceName)) return;
    addBusy(setTogglingPrivateSources, sourceName);
    try {
      const response = await api.post('csv/set_private', { source_name: sourceName, private: nextPrivate });
      if (response.data.success) {
        setSources((prev) => prev.map((s) =>
          s.source_name === sourceName ? { ...s, private: nextPrivate } : s
        ));
        notifySourcesChanged();
      }
    } catch (err) {
      setError(`Failed to update visibility: ${err.response?.data?.error || err.message}`);
    } finally {
      removeBusy(setTogglingPrivateSources, sourceName);
    }
  };

  const handleDownload = async (sourceName) => {
    if (downloadingSources.has(sourceName)) return;
    setDownloadingSources((prev) => {
      const next = new Set(prev);
      next.add(sourceName);
      return next;
    });
    try {
      const response = await api.get(`csv/download/${sourceName}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${sourceName}_with_embeddings.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(`Failed to download CSV: ${err.response?.data?.error || err.message}`);
    } finally {
      setDownloadingSources((prev) => {
        const next = new Set(prev);
        next.delete(sourceName);
        return next;
      });
    }
  };

  const handleUpdateDescription = async (sourceName) => {
    if (!editingDescription.trim()) { setError('Description cannot be empty'); return; }
    try {
      const response = await api.post('csv/update_description', {
        source_name: sourceName,
        description: editingDescription.trim()
      });
      if (response.data.success) {
        setSources((prev) => prev.map((s) =>
          s.source_name === sourceName ? { ...s, description: editingDescription.trim() } : s
        ));
        setEditingSource(null);
        setEditingDescription('');
        notifySourcesChanged();
      }
    } catch (err) {
      setError(`Failed to update description: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleStartEditing = (source) => {
    setEditingSource(source.source_name);
    setEditingDescription(source.description || '');
  };

  const handleCancelEditing = () => {
    setEditingSource(null);
    setEditingDescription('');
  };

  const handleAddScannedFile = async (scannedFile) => {
    setIsLoadingPreview(true);
    setShowAddForm(true);
    setNewCSV({ ...emptyNewCSV, path: scannedFile.path, sourceName: scannedFile.source_name });
    try {
      const response = await api.post('csv/preview', { path: scannedFile.path });
      if (response.data.success) {
        setPreview(response.data);
        setNewCSV((prev) => ({
          ...prev,
          delimiter: response.data.delimiter,
          vectorizedColumns: response.data.columns || []
        }));
      }
    } catch (err) {
      setError(`Failed to preview CSV: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleGenerateDescription = async () => {
    if (!newCSV.file && !newCSV.path) return;
    setIsGeneratingDescription(true);
    try {
      let response;
      const vectorizedColumns = newCSV.vectorizedColumns || [];
      if (newCSV.path) {
        response = await api.post('csv/generate_description', {
          path: newCSV.path,
          delimiter: newCSV.delimiter,
          vectorized_columns: vectorizedColumns
        });
      } else {
        const formData = new FormData();
        formData.append('file', newCSV.file);
        formData.append('delimiter', newCSV.delimiter);
        formData.append('vectorized_columns', JSON.stringify(vectorizedColumns));
        response = await api.post('csv/generate_description', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
      }
      if (response.data.success) {
        setNewCSV((prev) => ({ ...prev, description: response.data.description }));
      }
    } catch (err) {
      setError(`Failed to generate description: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsGeneratingDescription(false);
    }
  };

  const handleAddSource = async (e) => {
    e.preventDefault();
    if (!newCSV.file && !newCSV.path) { setError('Please select a CSV file'); return; }
    if (!newCSV.description) { setError('Description is required'); return; }
    if (!newCSV.vectorizedColumns || newCSV.vectorizedColumns.length === 0) {
      setError('Select at least one column to vectorize');
      return;
    }

    setIsAdding(true);
    setError(null);
    try {
      let response;
      const vectorizedColumnsJson = JSON.stringify(newCSV.vectorizedColumns);
      if (newCSV.path) {
        response = await api.post('csv/add', {
          path: newCSV.path,
          source_name: newCSV.sourceName,
          description: newCSV.description,
          delimiter: newCSV.delimiter,
          auto_detect_delimiter: false,
          auto_generate_description: false,
          vectorized_columns: newCSV.vectorizedColumns,
          private: currentUserIsAdmin ? !!newCSV.private : true
        });
      } else {
        const formData = new FormData();
        formData.append('file', newCSV.file);
        formData.append('description', newCSV.description);
        formData.append('delimiter', newCSV.delimiter);
        formData.append('auto_detect_delimiter', 'false');
        formData.append('auto_generate_description', 'false');
        formData.append('vectorized_columns', vectorizedColumnsJson);
        formData.append('private', (currentUserIsAdmin ? !!newCSV.private : true) ? 'true' : 'false');
        response = await api.post('csv/add', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
      }

      if (response.data.success) {
        await fetchSources();
        setNewCSV(emptyNewCSV);
        setPreview(null);
        setShowAddForm(false);
        notifySourcesChanged();
      }
    } catch (err) {
      setError(`Failed to add CSV: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsAdding(false);
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (file?.name.endsWith('.csv')) {
      setNewCSV((prev) => ({ ...prev, file, sourceName: file.name.replace(/\.csv$/, '') }));
      setPreview(null);
      setIsLoadingPreview(true);
      try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await api.post('csv/preview', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        if (response.data.success) {
          setPreview(response.data);
          setNewCSV((prev) => ({
            ...prev,
            delimiter: response.data.delimiter,
            vectorizedColumns: response.data.columns || []
          }));
        }
      } catch (err) {
        setError(`Failed to preview CSV: ${err.response?.data?.error || err.message}`);
      } finally {
        setIsLoadingPreview(false);
      }
    } else if (file) {
      setError('Please select a valid CSV file');
      e.target.value = null;
    }
  };

  const handleCancelAddForm = () => {
    setShowAddForm(false);
    setPreview(null);
    setNewCSV(emptyNewCSV);
  };

  const hasNoData = sources.length === 0 && scannedFiles.length === 0;

  return (
    <>
      <Modal show={show} onHide={requestClose} centered size="xl" dialogClassName="modal-90w">
        <Modal.Header closeButton data-bs-theme="light">
          <Modal.Title>Knowledge Base Manager</Modal.Title>
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
              Knowledge base collections are available to both the general chatbot and
              specialized agents. To activate or deactivate collections per agent, open
              that agent's settings under <strong>Administration</strong>.
            </small>
          </Alert>

          {showAddForm ? (
            <AddCSVForm
              newCSV={newCSV}
              setNewCSV={setNewCSV}
              preview={preview}
              isLoadingPreview={isLoadingPreview}
              isGeneratingDescription={isGeneratingDescription}
              isAdding={isAdding}
              currentUserIsAdmin={currentUserIsAdmin}
              onSubmit={handleAddSource}
              onCancel={handleCancelAddForm}
              onFileChange={handleFileChange}
              onGenerateDescription={handleGenerateDescription}
            />
          ) : (
            <Button
              variant="outline-dark"
              size="sm"
              className="mb-3"
              onClick={() => setShowAddForm(true)}
            >
              + Add CSV Source
            </Button>
          )}

          {isLoading && !showAddForm && (
            <div className="text-center p-4"><Spinner animation="border" /></div>
          )}

          {!isLoading && hasNoData && (
            <Alert variant="warning">
              No CSV sources configured. Click "Add CSV Source" to add one.
            </Alert>
          )}

          {!isLoading && !hasNoData && (
            <Table striped bordered hover size="sm" variant="light">
              <thead>
                <tr>
                  <th>Name</th>
                  <th style={{ width: '130px' }}>Status</th>
                  <th>Description</th>
                  <th style={{ width: '120px' }}>Owner</th>
                  <th style={{ width: '140px' }}>Uploaded</th>
                  <th style={{ width: '200px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <SourceRow
                    key={source.source_name}
                    source={source}
                    currentUsername={currentUsername}
                    editingSource={editingSource}
                    editingDescription={editingDescription}
                    onDelete={handleDelete}
                    onDownload={handleDownload}
                    isDownloading={downloadingSources.has(source.source_name)}
                    isDeleting={deletingSources.has(source.source_name)}
                    isTogglingPrivate={togglingPrivateSources.has(source.source_name)}
                    onTogglePrivate={handleTogglePrivate}
                    onStartEditing={handleStartEditing}
                    onUpdateDescription={handleUpdateDescription}
                    onCancelEditing={handleCancelEditing}
                    setEditingDescription={setEditingDescription}
                  />
                ))}
                {scannedFiles.map((scannedFile) => (
                  <ScannedFileRow
                    key={`scanned-${scannedFile.source_name}`}
                    scannedFile={scannedFile}
                    onAdd={handleAddScannedFile}
                  />
                ))}
              </tbody>
            </Table>
          )}

          <Alert variant="info" className="mb-3 py-2">
            <small>
              <strong>Note:</strong> Files in <code>sample_chatbot/sample_data/unstructured</code> are scanned automatically and shown
              as "Scanned" until someone adds them.
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

CSVManagerModal.propTypes = {
  show: PropTypes.bool.isRequired,
  handleClose: PropTypes.func.isRequired,
  hasActiveConversation: PropTypes.bool,
  selectedChatbot: PropTypes.object
};

export default CSVManagerModal;
