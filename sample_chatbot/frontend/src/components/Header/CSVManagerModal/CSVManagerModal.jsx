import React, { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Table from 'react-bootstrap/Table';
import api from '../../../api/client';
import { saveCSVConfigs } from './utils';
import AddCSVForm from './AddCSVForm';
import SourceRow from './SourceRow';
import ScannedFileRow from './ScannedFileRow';

const CSVManagerModal = ({ show, handleClose, onSourcesChange, selectedChatbot }) => {
  const [sources, setSources] = useState([]);
  const [scannedFiles, setScannedFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCSV, setNewCSV] = useState({
    file: null,
    description: '',
    delimiter: ';',
    path: null,
    sourceName: null
  });
  const [isAdding, setIsAdding] = useState(false);
  const [preview, setPreview] = useState(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isGeneratingDescription, setIsGeneratingDescription] = useState(false);
  const [editingSource, setEditingSource] = useState(null);
  const [editingDescription, setEditingDescription] = useState('');

  const syncActiveCsvsDict = useCallback((updatedSourcesList) => {
    const username = localStorage.getItem('current_user');
    if (!username) return;

    const agentKey = selectedChatbot && !selectedChatbot.isGlobal ? selectedChatbot.id : 'global';
    
    const dictString = localStorage.getItem(`${username}_active_csvs_dict`);
    let dict = {};
    if (dictString) {
      try { dict = JSON.parse(dictString); } catch (e) {}
    }

    dict[agentKey] = updatedSourcesList.filter(s => s.active).map(s => s.source_name);
    localStorage.setItem(`${username}_active_csvs_dict`, JSON.stringify(dict));
  }, [selectedChatbot]);

  // Fetch sources when modal opens
  const fetchSources = useCallback(async () => {
    if (!show) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get("csv/list");
      if (response.data.success) {
        const fetchedSources = response.data.sources || [];
        setSources(fetchedSources);

        // Update localStorage
        const username = localStorage.getItem('current_user');
        if (username) {
          saveCSVConfigs(username, fetchedSources);
          syncActiveCsvsDict(fetchedSources);
        }
      }
    } catch (err) {
      setError('Failed to load CSV sources');
      console.error('Error fetching CSV sources:', err);
    } finally {
      setIsLoading(false);
    }
  }, [show, syncActiveCsvsDict]);

  // Fetch scanned files from sample_data/unstructured folder
  const fetchScannedFiles = useCallback(async () => {
    if (!show) return;
    try {
      const response = await api.get("csv/scan");
      if (response.data.success) {
        // Filter out files that are already added as sources
        const sourceNames = new Set(sources.map((s) => s.source_name));
        const newScanned = (response.data.files || []).filter(
          (f) => !sourceNames.has(f.source_name)
        );
        setScannedFiles(newScanned);
      }
    } catch (err) {
      console.error('Error scanning CSV files:', err);
    }
  }, [show, sources]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  useEffect(() => {
    fetchScannedFiles();
  }, [fetchScannedFiles]);

  // Toggle source active status
  const handleToggleActive = async (sourceName, currentActive) => {
    // Check if source has a description before allowing activation
    const source = sources.find((s) => s.source_name === sourceName);
    if (!currentActive && source && !source.description?.trim()) {
      setError('Cannot activate source without a description. Please add a description first.');
      return;
    }

    try {
      const response = await api.post("csv/activate", {
        source_name: sourceName,
        active: !currentActive
      });
      if (response.data.success) {
        const updatedSources = sources.map((s) =>
          s.source_name === sourceName ? { ...s, active: !currentActive } : s
        );
        setSources(updatedSources);

        // Update localStorage
        const username = localStorage.getItem('current_user');
        if (username) {
          saveCSVConfigs(username, updatedSources);
          syncActiveCsvsDict(updatedSources);
        }
        if (onSourcesChange) onSourcesChange();
      }
    } catch (err) {
      setError(`Failed to toggle source: ${err.response?.data?.error || err.message}`);
    }
  };

  // Delete a source
  const handleDelete = async (sourceName, deleteFile = false) => {
    const confirmMessage = `Are you sure you want to delete "${sourceName}"?${
      deleteFile ? ' The CSV file will also be deleted.' : ''
    }`;
    if (!window.confirm(confirmMessage)) {
      return;
    }
    try {
      const response = await api.delete(`csv/delete/${sourceName}`, {
        data: { delete_file: deleteFile }
      });
      if (response.data.success) {
        const updatedSources = sources.filter((s) => s.source_name !== sourceName);
        setSources(updatedSources);

        // Update localStorage
        const username = localStorage.getItem('current_user');
        if (username) {
          saveCSVConfigs(username, updatedSources);
          syncActiveCsvsDict(updatedSources);
        }
        if (onSourcesChange) onSourcesChange();
      }
    } catch (err) {
      setError(`Failed to delete source: ${err.response?.data?.error || err.message}`);
    }
  };

  // Update description
  const handleUpdateDescription = async (sourceName) => {
    if (!editingDescription.trim()) {
      setError('Description cannot be empty');
      return;
    }
    try {
      const response = await api.post("csv/update_description", {
        source_name: sourceName,
        description: editingDescription.trim()
      });
      if (response.data.success) {
        setSources((prev) =>
          prev.map((s) =>
            s.source_name === sourceName ? { ...s, description: editingDescription.trim() } : s
          )
        );
        // Update localStorage
        const username = localStorage.getItem('current_user');
        if (username) {
          const updatedSources = sources.map((s) =>
            s.source_name === sourceName ? { ...s, description: editingDescription.trim() } : s
          );
          saveCSVConfigs(username, updatedSources);
        }
        setEditingSource(null);
        setEditingDescription('');
        if (onSourcesChange) onSourcesChange();
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

  // Open add form with scanned file data pre-populated
  const handleAddScannedFile = async (scannedFile) => {
    setIsLoadingPreview(true);
    setShowAddForm(true);
    setNewCSV({
      file: null,
      description: '',
      delimiter: ';',
      path: scannedFile.path,
      sourceName: scannedFile.source_name
    });

    // Auto-preview the scanned file by path
    try {
      const response = await api.post("csv/preview", {
        path: scannedFile.path
      });
      if (response.data.success) {
        setPreview(response.data);
        setNewCSV((prev) => ({ ...prev, delimiter: response.data.delimiter }));
      }
    } catch (err) {
      setError(`Failed to preview CSV: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  // Generate description using AI
  const handleGenerateDescription = async () => {
    if (!newCSV.file && !newCSV.path) return;

    setIsGeneratingDescription(true);
    try {
      let response;
      if (newCSV.path) {
        // Path-based (scanned file)
        response = await api.post("csv/generate_description", {
          path: newCSV.path,
          delimiter: newCSV.delimiter
        });
      } else {
        // File upload
        const formData = new FormData();
        formData.append('file', newCSV.file);
        formData.append('delimiter', newCSV.delimiter);
        response = await api.post("csv/generate_description", formData, {
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

  // Add new CSV source
  const handleAddSource = async (e) => {
    e.preventDefault();
    if (!newCSV.file && !newCSV.path) {
      setError('Please select a CSV file');
      return;
    }
    if (!newCSV.description) {
      setError('Description is required');
      return;
    }

    setIsAdding(true);
    setError(null);
    try {
      let response;
      if (newCSV.path) {
        // Path-based (scanned file)
        response = await api.post("csv/add", {
          path: newCSV.path,
          source_name: newCSV.sourceName,
          description: newCSV.description,
          delimiter: newCSV.delimiter,
          auto_detect_delimiter: false,
          auto_generate_description: false
        });
      } else {
        // File upload
        const formData = new FormData();
        formData.append('file', newCSV.file);
        formData.append('description', newCSV.description);
        formData.append('delimiter', newCSV.delimiter);
        formData.append('auto_detect_delimiter', 'false');
        formData.append('auto_generate_description', 'false');
        response = await api.post("csv/add", formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
      }

      if (response.data.success) {
        // Refresh the list
        await fetchSources();
        // Reset form
        setNewCSV({
          file: null,
          description: '',
          delimiter: ';',
          path: null,
          sourceName: null
        });
        setPreview(null);
        setShowAddForm(false);
        if (onSourcesChange) onSourcesChange();
      }
    } catch (err) {
      setError(`Failed to add CSV: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsAdding(false);
    }
  };

  // Handle file selection - auto-preview immediately
  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (file?.name.endsWith('.csv')) {
      setNewCSV((prev) => ({ ...prev, file }));
      setPreview(null);
      setIsLoadingPreview(true);

      // Auto-preview the file
      try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await api.post("csv/preview", formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        if (response.data.success) {
          setPreview(response.data);
          setNewCSV((prev) => ({ ...prev, delimiter: response.data.delimiter }));
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
    setNewCSV({
      file: null,
      description: '',
      delimiter: ';',
      path: null,
      sourceName: null
    });
  };

  const hasNoData = sources.length === 0 && scannedFiles.length === 0;

  return (
    <Modal show={show} onHide={handleClose} centered size="xl" dialogClassName="modal-90w">
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>Knowledge Base Manager</Modal.Title>
      </Modal.Header>
      <Modal.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
        {error && (
          <Alert variant="danger" onClose={() => setError(null)} dismissible>
            {error}
          </Alert>
        )}

        {/* Add New CSV Form */}
        {showAddForm ? (
          <AddCSVForm
            newCSV={newCSV}
            setNewCSV={setNewCSV}
            preview={preview}
            isLoadingPreview={isLoadingPreview}
            isGeneratingDescription={isGeneratingDescription}
            isAdding={isAdding}
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

        {/* Sources List */}
        {isLoading && !showAddForm && (
          <div className="text-center p-4">
            <Spinner animation="border" />
          </div>
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
                <th style={{ width: '70px' }}>Active</th>
                <th>Name</th>
                <th>Description</th>
                <th style={{ width: '130px' }}>Status</th>
                <th style={{ width: '100px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {/* Configured sources */}
              {sources.map((source) => (
                <SourceRow
                  key={source.source_name}
                  source={source}
                  editingSource={editingSource}
                  editingDescription={editingDescription}
                  onToggleActive={handleToggleActive}
                  onDelete={handleDelete}
                  onStartEditing={handleStartEditing}
                  onUpdateDescription={handleUpdateDescription}
                  onCancelEditing={handleCancelEditing}
                  setEditingDescription={setEditingDescription}
                />
              ))}

              {/* Scanned files (not yet added) */}
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
            <strong>Note:</strong> Active sources are used when answering knowledge base queries.
            Toggle sources on/off to control which CSVs are searched.
            <br />
            Files in <code>sample_chatbot/sample_data/unstructured</code> are automatically scanned
            and shown here. To make them usable by the chatbot, please write a useful description
            and add them.
          </small>
        </Alert>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="light" onClick={handleClose}>
          Close
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

CSVManagerModal.propTypes = {
  show: PropTypes.bool.isRequired,
  handleClose: PropTypes.func.isRequired,
  onSourcesChange: PropTypes.func,
  selectedChatbot: PropTypes.object
};

export default CSVManagerModal;
