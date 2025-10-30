import React, { createContext, useState, useContext, useCallback } from 'react';
import axios from 'axios';

// Create the context
const PDFContext = createContext();

// PDF status constants
export const PDF_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing', 
  COMPLETED: 'completed',
  FAILED: 'failed'
};

// Create a provider component
export const PDFProvider = ({ children }) => {
  const [pdfs, setPdfs] = useState([]); // Array of PDF objects
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Generate a PDF from DeepQuery metadata
  const generatePDF = useCallback(async (deepqueryMetadata, question, colorPalette = 'red') => {
    const pdfId = `pdf_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Extract report title from metadata, fallback to question if not available
    const reportTitle = deepqueryMetadata?.analysis_title || question || 'Untitled Report';
    
    // Add to pending list
    const newPdf = {
      id: pdfId,
      question: question,
      reportTitle: reportTitle,
      status: PDF_STATUS.PENDING,
      createdAt: new Date(),
      colorPalette: colorPalette,
      metadata: deepqueryMetadata,
      downloadUrl: null,
      error: null
    };
    
    setPdfs(prev => [...prev, newPdf]);
    
    try {
      // Update status to processing
      setPdfs(prev => prev.map(pdf => 
        pdf.id === pdfId 
          ? { ...pdf, status: PDF_STATUS.PROCESSING }
          : pdf
      ));
      
      // Call the generateDeepQueryPDF endpoint
      const response = await axios.post('generate_pdf', {
        deepquery_metadata: deepqueryMetadata,
        color_palette: colorPalette
      });
      
      if (response.data.pdf_blob) {
        // Create blob URL for download
        const binaryString = atob(response.data.pdf_blob);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: 'application/pdf' });
        const downloadUrl = URL.createObjectURL(blob);
        
        // Update with completed status
        setPdfs(prev => prev.map(pdf => 
          pdf.id === pdfId 
            ? { 
                ...pdf, 
                status: PDF_STATUS.COMPLETED,
                completedAt: new Date(),
                downloadUrl: downloadUrl,
                filename: response.data.pdf_path || `${pdfId}_report.pdf`
              }
            : pdf
        ));
      } else {
        throw new Error('No PDF blob received');
      }
      
    } catch (error) {
      console.error('Error generating PDF:', error);
      setPdfs(prev => prev.map(pdf => 
        pdf.id === pdfId 
          ? { 
              ...pdf, 
              status: PDF_STATUS.FAILED,
              completedAt: new Date(),
              error: error.response?.data?.error || error.message
            }
          : pdf
      ));
    }
    
    return pdfId;
  }, []);
  
  // Remove a PDF from the list
  const removePDF = useCallback((pdfId) => {
    setPdfs(prev => {
      const pdfToRemove = prev.find(pdf => pdf.id === pdfId);
      if (pdfToRemove && pdfToRemove.downloadUrl) {
        URL.revokeObjectURL(pdfToRemove.downloadUrl);
      }
      return prev.filter(pdf => pdf.id !== pdfId);
    });
  }, []);
  
  // Clear all PDFs
  const clearAllPDFs = useCallback(() => {
    pdfs.forEach(pdf => {
      if (pdf.downloadUrl) {
        URL.revokeObjectURL(pdf.downloadUrl);
      }
    });
    setPdfs([]);
  }, [pdfs]);
  
  // Get counts by status
  const getStatusCounts = useCallback(() => {
    return pdfs.reduce((counts, pdf) => {
      counts[pdf.status] = (counts[pdf.status] || 0) + 1;
      return counts;
    }, {});
  }, [pdfs]);
  
  const value = {
    pdfs,
    isModalOpen,
    setIsModalOpen,
    generatePDF,
    removePDF,
    clearAllPDFs,
    getStatusCounts
  };

  return (
    <PDFContext.Provider value={value}>
      {children}
    </PDFContext.Provider>
  );
};

// Create a custom hook to use the PDF context
export const usePDF = () => {
  const context = useContext(PDFContext);
  if (context === undefined) {
    throw new Error('usePDF must be used within a PDFProvider');
  }
  return context;
};

export default PDFContext; 