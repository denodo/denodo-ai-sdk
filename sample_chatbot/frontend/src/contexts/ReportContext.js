import React, { createContext, useState, useContext, useCallback } from 'react';
import axios from 'axios';

// Create the context
const ReportContext = createContext();

// Report status constants
export const REPORT_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing', 
  COMPLETED: 'completed',
  FAILED: 'failed'
};

// Create a provider component
export const ReportProvider = ({ children }) => {
  const [reports, setReports] = useState([]); // Array of report objects
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Generate a report from DeepQuery metadata
  const generateReport = useCallback(async (deepqueryMetadata, question, colorPalette = 'red') => {
    const reportId = `report_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Extract report title from metadata, fallback to question if not available
    const reportTitle = deepqueryMetadata?.analysis_title || question || 'Untitled Report';
    
    // Add to pending list
    const newReport = {
      id: reportId,
      question: question,
      reportTitle: reportTitle,
      status: REPORT_STATUS.PENDING,
      createdAt: new Date(),
      colorPalette: colorPalette,
      metadata: deepqueryMetadata,
      downloadUrl: null,
      error: null
    };
    
    setReports(prev => [...prev, newReport]);
    
    try {
      // Update status to processing
      setReports(prev => prev.map(report => 
        report.id === reportId 
          ? { ...report, status: REPORT_STATUS.PROCESSING }
          : report
      ));
      
      // Call the generate report endpoint
      const response = await axios.post('generate_report', {
        deepquery_metadata: deepqueryMetadata,
        color_palette: colorPalette
      });

      const htmlReport = response.data.html_report;

      if (htmlReport) {
        const blob = new Blob([htmlReport], { type: 'text/html' });
        const downloadUrl = URL.createObjectURL(blob);

        const safeTitle = reportTitle
          ? reportTitle.replace(/[^a-z0-9]/gi, '_').toLowerCase()
          : reportId;
        const filename = `${safeTitle}_report.html`;

        setReports(prev => prev.map(report => 
          report.id === reportId 
            ? { 
                ...report, 
                status: REPORT_STATUS.COMPLETED,
                completedAt: new Date(),
                downloadUrl: downloadUrl,
                filename: filename
              }
            : report
        ));
      } else {
        throw new Error('No HTML report received');
      }
      
    } catch (error) {
      console.error('Error generating report:', error);
      setReports(prev => prev.map(report => 
        report.id === reportId 
          ? { 
              ...report, 
              status: REPORT_STATUS.FAILED,
              completedAt: new Date(),
              error: error.response?.data?.error || error.message
            }
          : report
      ));
    }
    
    return reportId;
  }, []);
  
  // Remove a report from the list
  const removeReport = useCallback((reportId) => {
    setReports(prev => {
      const toRemove = prev.find(report => report.id === reportId);
      if (toRemove && toRemove.downloadUrl) {
        URL.revokeObjectURL(toRemove.downloadUrl);
      }
      return prev.filter(report => report.id !== reportId);
    });
  }, []);
  
  // Clear all reports
  const clearAllReports = useCallback(() => {
    reports.forEach(report => {
      if (report.downloadUrl) {
        URL.revokeObjectURL(report.downloadUrl);
      }
    });
    setReports([]);
  }, [reports]);
  
  // Get counts by status
  const getStatusCounts = useCallback(() => {
    return reports.reduce((counts, report) => {
      counts[report.status] = (counts[report.status] || 0) + 1;
      return counts;
    }, {});
  }, [reports]);
  
  const value = {
    reports,
    isModalOpen,
    setIsModalOpen,
    generateReport,
    removeReport,
    clearAllReports,
    getStatusCounts
  };

  return (
    <ReportContext.Provider value={value}>
      {children}
    </ReportContext.Provider>
  );
};

// Create a custom hook to use the report context
export const useReport = () => {
  const context = useContext(ReportContext);
  if (context === undefined) {
    throw new Error('useReport must be used within a ReportProvider');
  }
  return context;
};

export default ReportContext; 