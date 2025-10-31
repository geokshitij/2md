"""
Flask Web UI for PDF to Markdown Conversion
Provides upload, progress tracking, and download functionality
"""

import os
import uuid
import json
import threading
import logging
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
from gptpdf import parse_pdf
import shutil
import concurrent.futures

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Store processing status
processing_status = {}
# Thread pool for parallel processing
pdf_executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF to Markdown Converter</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            padding: 30px 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .layout {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            align-items: start;
        }
        
        .left-panel, .right-panel {
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            padding: 35px;
            border: 1px solid rgba(0,0,0,0.05);
        }
        
        .right-panel {
            position: sticky;
            top: 30px;
            max-height: calc(100vh - 60px);
            overflow-y: auto;
        }
        
        .right-panel::-webkit-scrollbar {
            width: 8px;
        }
        
        .right-panel::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 10px;
        }
        
        .right-panel::-webkit-scrollbar-thumb {
            background: #888;
            border-radius: 10px;
        }
        
        .right-panel::-webkit-scrollbar-thumb:hover {
            background: #555;
        }
        
        h1 {
            color: #1a202c;
            text-align: center;
            margin-bottom: 8px;
            font-size: 2.5em;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        
        .subtitle {
            text-align: center;
            color: #718096;
            margin-bottom: 40px;
            font-size: 1.05em;
            font-weight: 400;
        }
        
        .job-list {
            margin-top: 0;
        }
        
        .panel-header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e2e8f0;
        }
        
        .panel-header h2 {
            margin: 0 0 8px 0;
            color: #1a202c;
            font-size: 1.75em;
            font-weight: 700;
            letter-spacing: -0.01em;
        }
        
        .panel-header p {
            margin: 0;
            color: #718096;
            font-size: 0.95em;
        }
        
        .job-card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            border: 2px solid #e2e8f0;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }
        
        .job-card:hover {
            box-shadow: 0 8px 24px rgba(0,0,0,0.08);
            transform: translateY(-3px);
        }
        
        .job-card.processing {
            border-color: #667eea;
            background: linear-gradient(to right, #ffffff 0%, #f7f9ff 100%);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
        }
        
        .job-card.completed {
            border-color: #48bb78;
            background: linear-gradient(to right, #ffffff 0%, #f0fff4 100%);
            box-shadow: 0 4px 12px rgba(72, 187, 120, 0.15);
        }
        
        .job-card.failed {
            border-color: #f56565;
            background: linear-gradient(to right, #ffffff 0%, #fff5f5 100%);
            box-shadow: 0 4px 12px rgba(245, 101, 101, 0.15);
        }
        
        .job-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        
        .job-title {
            font-weight: 600;
            color: #1a202c;
            font-size: 1.05em;
            flex: 1;
            margin-right: 12px;
            word-break: break-word;
        }
        
        .job-status {
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }
        
        .status-processing {
            background: #667eea;
            color: white;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
        }
        
        .status-completed {
            background: #48bb78;
            color: white;
            box-shadow: 0 2px 8px rgba(72, 187, 120, 0.3);
        }
        
        .status-failed {
            background: #f56565;
            color: white;
            box-shadow: 0 2px 8px rgba(245, 101, 101, 0.3);
        }
        
        .status-queued {
            background: #ecc94b;
            color: #744210;
            box-shadow: 0 2px 8px rgba(236, 201, 75, 0.3);
        }
        
        .upload-section {
            margin-bottom: 30px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            color: #2d3748;
            font-weight: 600;
            font-size: 0.95em;
        }
        
        .file-name {
            margin-top: 10px;
            color: #666;
            font-style: italic;
        }
        
        .file-list {
            margin-top: 10px;
            max-height: 150px;
            overflow-y: auto;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        
        .file-list-item {
            padding: 5px 0;
            color: #555;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .file-list-item:last-child {
            border-bottom: none;
        }
        
        .parallel-info {
            background: linear-gradient(135deg, #ebf8ff 0%, #e6fffa 100%);
            padding: 16px 20px;
            border-radius: 10px;
            margin: 15px 0;
            color: #2c5282;
            font-size: 0.9em;
            border: 2px solid #bee3f8;
            font-weight: 500;
        }
        
        .info-banner {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.25);
        }
        
        .info-banner h3 {
            margin: 0 0 8px 0;
            font-size: 1.25em;
            font-weight: 600;
        }
        
        .info-banner p {
            margin: 4px 0;
            opacity: 0.95;
            font-size: 0.95em;
            line-height: 1.5;
        }
        
        .success-message {
            background: #f0fff4;
            color: #22543d;
            padding: 16px 20px;
            border-radius: 10px;
            margin: 15px 0;
            border: 2px solid #9ae6b4;
            display: none;
            font-weight: 500;
            box-shadow: 0 2px 8px rgba(72, 187, 120, 0.15);
        }
        
        .processing-count {
            background: linear-gradient(135deg, #fef5e7 0%, #fdebd0 100%);
            color: #744210;
            padding: 14px 20px;
            border-radius: 10px;
            margin: 0 0 20px 0;
            text-align: center;
            font-weight: 600;
            display: none;
            border: 2px solid #f6e05e;
            box-shadow: 0 2px 8px rgba(236, 201, 75, 0.2);
        }
        
        input[type="text"], input[type="number"] {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e2e8f0;
            border-radius: 10px;
            font-size: 15px;
            transition: all 0.2s ease;
            background: #f7fafc;
            color: #2d3748;
            font-family: inherit;
        }
        
        input[type="text"]:hover, input[type="number"]:hover {
            border-color: #cbd5e0;
            background: white;
        }
        
        input[type="text"]:focus, input[type="number"]:focus {
            outline: none;
            border-color: #667eea;
            background: white;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        .btn {
            padding: 14px 40px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: inline-block;
            text-decoration: none;
            text-align: center;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            width: 100%;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
            font-weight: 600;
        }
        
        .btn-primary::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
            transition: left 0.5s;
        }
        
        .btn-primary:hover:not(:disabled)::before {
            left: 100%;
        }
        
        .btn-primary:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 12px 28px rgba(102, 126, 234, 0.4);
        }
        
        .btn-primary:active:not(:disabled) {
            transform: translateY(0);
        }
        
        .btn-primary:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .btn-primary.processing {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            opacity: 0.9;
        }
        
        .btn-success {
            background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
            color: white;
            margin: 5px;
            box-shadow: 0 2px 8px rgba(72, 187, 120, 0.3);
            font-weight: 600;
        }
        
        .btn-success:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(72, 187, 120, 0.4);
        }
        
        .btn-info {
            background: linear-gradient(135deg, #4299e1 0%, #3182ce 100%);
            color: white;
            margin: 5px;
            box-shadow: 0 2px 8px rgba(66, 153, 225, 0.3);
            font-weight: 600;
        }
        
        .btn-info:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(66, 153, 225, 0.4);
        }
        
        .progress-section {
            display: none;
            margin-top: 30px;
        }
        
        .progress-bar-container {
            width: 100%;
            height: 12px;
            background: #e2e8f0;
            border-radius: 20px;
            overflow: hidden;
            margin-bottom: 12px;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);
        }
        
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.4s ease;
            border-radius: 20px;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
        }
        
        .progress-text {
            font-size: 0.85em;
            color: #4a5568;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .status-message {
            color: #718096;
            margin-bottom: 16px;
            font-size: 0.9em;
            line-height: 1.5;
        }
        
        .download-section {
            display: none;
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        
        .download-buttons {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
        }
        
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .image-list {
            margin-top: 20px;
        }
        
        .image-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            background: white;
            margin: 5px 0;
            border-radius: 5px;
            border: 1px solid #e0e0e0;
        }
        
        .advanced-options {
            margin-top: 20px;
            padding: 20px;
            background: #f7fafc;
            border-radius: 12px;
            border: 2px solid #e2e8f0;
            transition: all 0.3s ease;
        }
        
        .advanced-options:hover {
            border-color: #cbd5e0;
        }
        
        .options-header {
            cursor: pointer;
            user-select: none;
            font-weight: 600;
            color: #667eea;
            margin-bottom: 15px;
            transition: color 0.2s;
        }
        
        .options-header:hover {
            color: #764ba2;
        }
        
        .options-content {
            display: none;
        }
        
        .options-content.active {
            display: block;
        }
        
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        
        .download-all-container {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            text-align: center;
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3);
        }
        
        .download-all-container h3 {
            margin: 0 0 8px 0;
            font-size: 1.15em;
            font-weight: 600;
        }
        
        .download-all-container p {
            margin: 0 0 16px 0;
            opacity: 0.95;
            font-size: 0.9em;
        }
        
        .btn-download-all {
            background: white;
            color: #667eea;
            padding: 12px 32px;
            border-radius: 10px;
            text-decoration: none;
            display: inline-block;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        
        .btn-download-all:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        }
        
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            color: #a0aec0;
        }
        
        .empty-state-icon {
            font-size: 4.5em;
            margin-bottom: 20px;
            opacity: 0.4;
        }
        
        .empty-state h3 {
            color: #4a5568;
            font-size: 1.25em;
            margin-bottom: 8px;
            font-weight: 600;
        }
        
        .empty-state p {
            color: #718096;
            font-size: 0.95em;
        }
        
        @media (max-width: 1024px) {
            .layout {
                grid-template-columns: 1fr;
            }
            
            .right-panel {
                position: relative;
                top: 0;
                max-height: none;
            }
        }
        
        @media (max-width: 600px) {
            .container {
                padding: 10px;
            }
            
            .left-panel, .right-panel {
                padding: 20px;
            }
            
            h1 {
                font-size: 2em;
            }
            
            .grid-2 {
                grid-template-columns: 1fr;
            }
            
            .download-buttons {
                flex-direction: column;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 style="text-align: center; margin-bottom: 10px;">PDF to Markdown</h1>
        <p style="text-align: center; color: #666; margin-bottom: 30px;">Convert your PDF documents to Markdown with AI</p>
        
        <div class="layout">
            <!-- Left Panel: Upload Form -->
            <div class="left-panel">
                <div class="panel-header">
                    <h2>Upload & Configure</h2>
                    <p>Select PDFs and set conversion parameters</p>
                </div>
                
                <div class="success-message" id="successMessage"></div>
                
                <div class="upload-section">
            <form id="uploadForm">
                <div class="form-group">
                    <label>Select PDF Files (Multiple):</label>
                    <input type="file" id="pdfFile" name="pdfs" accept=".pdf" multiple required 
                           style="display: block; padding: 10px; border: 2px dashed #667eea; 
                           border-radius: 8px; cursor: pointer;">
                    <div class="file-list" id="fileList" style="display: none;"></div>
                </div>
                
                <div class="parallel-info">
                    Multiple PDFs will be processed in parallel for faster conversion
                </div>
                
                <div class="form-group">
                    <label for="apiKey">OpenAI API Key:</label>
                    <input type="text" id="apiKey" name="api_key" 
                           placeholder="sk-..." required autocomplete="off">
                    <small style="color: #666; font-size: 0.85em;">Your API key is saved locally in this session</small>
                </div>
                
                <div class="advanced-options">
                    <div class="options-header" onclick="toggleOptions()">
                        Advanced Options (Click to expand)
                    </div>
                    <div class="options-content" id="advancedOptions">
                        <div class="grid-2">
                            <div class="form-group">
                                <label for="baseUrl">Base URL (optional):</label>
                                <input type="text" id="baseUrl" name="base_url" 
                                       placeholder="https://api.openai.com/v1">
                            </div>
                            
                            <div class="form-group">
                                <label for="model">Model:</label>
                                <input type="text" id="model" name="model" 
                                       value="gpt-4o" placeholder="gpt-4o">
                            </div>
                            
                            <div class="form-group">
                                <label for="workers">GPT Workers per PDF:</label>
                                <input type="number" id="workers" name="gpt_worker" 
                                       value="1" min="1" max="10">
                            </div>
                            
                            <div class="form-group">
                                <label for="maxParallel">Max Parallel PDFs:</label>
                                <input type="number" id="maxParallel" name="max_parallel" 
                                       value="3" min="1" max="5">
                            </div>
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="btn btn-primary" id="submitBtn">
                    Start Conversion
                </button>
            </form>
        </div>
    </div>
    
    <!-- Right Panel: Progress Tracking -->
    <div class="right-panel">
        <div class="panel-header">
            <h2>Progress Tracker</h2>
            <p>Monitor your conversions in real-time</p>
        </div>
        
        <div class="processing-count" id="processingCount"></div>
        
        <div id="downloadAllSection" style="display: none;">
            <div class="download-all-container">
                <h3>Download All Completed PDFs</h3>
                <p style="margin: 10px 0;">Get all processed files in one ZIP</p>
                <a href="#" id="downloadAllBtn" class="btn-download-all">
                    Download All PDFs (ZIP)
                </a>
            </div>
        </div>
        
        <div class="job-list" id="jobList">
            <div class="empty-state">
                <div class="empty-state-icon">📄</div>
                <h3>No active conversions</h3>
                <p>Upload PDFs from the left panel to start</p>
            </div>
        </div>
    </div>
</div>
    
    <script>
        let activeJobs = new Set();
        let completedJobs = new Set();
        let allJobStatuses = {};
        let pollingInterval = null;
        let savedApiKey = '';
        let savedBaseUrl = '';
        let savedModel = 'gpt-4o';
        let savedWorkers = 1;
        let savedMaxParallel = 3;
        
        // Load saved values from localStorage
        window.addEventListener('load', function() {
            savedApiKey = localStorage.getItem('apiKey') || '';
            savedBaseUrl = localStorage.getItem('baseUrl') || '';
            savedModel = localStorage.getItem('model') || 'gpt-4o';
            savedWorkers = localStorage.getItem('workers') || 1;
            savedMaxParallel = localStorage.getItem('maxParallel') || 3;
            
            if (savedApiKey) document.getElementById('apiKey').value = savedApiKey;
            if (savedBaseUrl) document.getElementById('baseUrl').value = savedBaseUrl;
            if (savedModel) document.getElementById('model').value = savedModel;
            if (savedWorkers) document.getElementById('workers').value = savedWorkers;
            if (savedMaxParallel) document.getElementById('maxParallel').value = savedMaxParallel;
        });
        
        // Save values to localStorage when changed
        document.getElementById('apiKey').addEventListener('change', function(e) {
            savedApiKey = e.target.value;
            localStorage.setItem('apiKey', savedApiKey);
        });
        
        document.getElementById('baseUrl').addEventListener('change', function(e) {
            savedBaseUrl = e.target.value;
            localStorage.setItem('baseUrl', savedBaseUrl);
        });
        
        document.getElementById('model').addEventListener('change', function(e) {
            savedModel = e.target.value;
            localStorage.setItem('model', savedModel);
        });
        
        document.getElementById('workers').addEventListener('change', function(e) {
            savedWorkers = e.target.value;
            localStorage.setItem('workers', savedWorkers);
        });
        
        document.getElementById('maxParallel').addEventListener('change', function(e) {
            savedMaxParallel = e.target.value;
            localStorage.setItem('maxParallel', savedMaxParallel);
        });
        
        // File selection handler
        document.getElementById('pdfFile').addEventListener('change', function(e) {
            const fileList = document.getElementById('fileList');
            if (e.target.files.length > 0) {
                let html = '<strong>Selected files:</strong><br>';
                for (let i = 0; i < e.target.files.length; i++) {
                    html += `<div class="file-list-item">${i + 1}. ${e.target.files[i].name}</div>`;
                }
                fileList.innerHTML = html;
                fileList.style.display = 'block';
            } else {
                fileList.style.display = 'none';
            }
        });
        
        // Toggle advanced options
        function toggleOptions() {
            const options = document.getElementById('advancedOptions');
            options.classList.toggle('active');
        }
        
        // Form submission
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const submitBtn = document.getElementById('submitBtn');
            const fileInput = document.getElementById('pdfFile');
            const fileCount = fileInput.files.length;
            
            submitBtn.disabled = true;
            submitBtn.classList.add('processing');
            submitBtn.textContent = 'Uploading ' + fileCount + ' file(s)...';
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    result.job_ids.forEach(jobId => activeJobs.add(jobId));
                    
                    // Store all job IDs for batch download
                    let allJobs = JSON.parse(localStorage.getItem('allJobs') || '[]');
                    allJobs = [...new Set([...allJobs, ...result.job_ids])];
                    localStorage.setItem('allJobs', JSON.stringify(allJobs));
                    
                    startPolling();
                    
                    // Show success message
                    const successMsg = document.getElementById('successMessage');
                    successMsg.textContent = `Successfully queued ${result.count} PDF(s) for processing!`;
                    successMsg.style.display = 'block';
                    setTimeout(() => {
                        successMsg.style.display = 'none';
                    }, 5000);
                    
                    // Update processing count
                    updateProcessingCount();
                    
                    // Reset only the file input, keep other fields
                    fileInput.value = '';
                    document.getElementById('fileList').style.display = 'none';
                    
                    submitBtn.disabled = false;
                    submitBtn.classList.remove('processing');
                    submitBtn.textContent = 'Start Conversion';
                } else {
                    alert('Error: ' + result.error);
                    submitBtn.disabled = false;
                    submitBtn.classList.remove('processing');
                    submitBtn.textContent = 'Start Conversion';
                }
            } catch (error) {
                alert('Error: ' + error.message);
                submitBtn.disabled = false;
                submitBtn.classList.remove('processing');
                submitBtn.textContent = 'Start Conversion';
            }
        });
        
        function updateProcessingCount() {
            const count = activeJobs.size;
            const countDiv = document.getElementById('processingCount');
            if (count > 0) {
                countDiv.textContent = `Currently processing ${count} PDF(s)...`;
                countDiv.style.display = 'block';
            } else {
                countDiv.style.display = 'none';
            }
        }
        
        // Poll for status
        function startPolling() {
            if (pollingInterval) return;
            
            pollingInterval = setInterval(async () => {
                if (activeJobs.size === 0 && completedJobs.size === 0) {
                    stopPolling();
                    updateProcessingCount();
                    return;
                }
                
                try {
                    // Get status for active jobs only
                    const jobIds = Array.from(activeJobs);
                    const response = await fetch('/status/batch', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({job_ids: jobIds})
                    });
                    
                    const statuses = await response.json();
                    
                    // Update stored statuses
                    statuses.forEach(status => {
                        allJobStatuses[status.job_id] = status;
                        
                        // Move completed/failed jobs from active to completed
                        if (status.status === 'completed') {
                            activeJobs.delete(status.job_id);
                            completedJobs.add(status.job_id);
                        } else if (status.status === 'failed') {
                            activeJobs.delete(status.job_id);
                        }
                    });
                    
                    // Build array of all statuses (active + completed)
                    const allStatuses = Object.values(allJobStatuses);
                    updateJobList(allStatuses);
                    
                    updateProcessingCount();
                } catch (error) {
                    console.error('Polling error:', error);
                }
            }, 1000);
        }
        
        function stopPolling() {
            if (pollingInterval) {
                clearInterval(pollingInterval);
                pollingInterval = null;
            }
        }
        
        function updateJobList(statuses) {
            const jobList = document.getElementById('jobList');
            if (statuses.length === 0) {
                jobList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📄</div>
                        <h3>No active conversions</h3>
                        <p>Upload PDFs from the left panel to start</p>
                    </div>
                `;
                return;
            }
            
            // Sort: processing first, then completed, then failed
            statuses.sort((a, b) => {
                const order = {'processing': 0, 'queued': 1, 'completed': 2, 'failed': 3};
                return order[a.status] - order[b.status];
            });
            
            // Check if there are completed jobs
            const completedJobsList = statuses.filter(s => s.status === 'completed');
            const downloadAllSection = document.getElementById('downloadAllSection');
            const downloadAllBtn = document.getElementById('downloadAllBtn');
            
            if (completedJobsList.length > 0) {
                downloadAllSection.style.display = 'block';
                const allJobIds = completedJobsList.map(s => s.job_id);
                const jobIdsParam = allJobIds.join(',');
                downloadAllBtn.href = `/download/all?job_ids=${jobIdsParam}`;
                
                console.log('Completed jobs:', completedJobsList.length, 'IDs:', jobIdsParam);
                
                // Update button text with count
                const btnText = completedJobsList.length === 1 ? 
                    'Download PDF (ZIP)' : 
                    `Download All ${completedJobsList.length} PDFs (ZIP)`;
                downloadAllBtn.textContent = btnText;
            } else {
                downloadAllSection.style.display = 'none';
            }
            
            let html = '';
            statuses.forEach(status => {
                const statusClass = status.status === 'completed' ? 'completed' : 
                                  status.status === 'failed' ? 'failed' : 'processing';
                const statusLabel = status.status.charAt(0).toUpperCase() + status.status.slice(1);
                
                // Add animation for processing jobs
                const animationStyle = status.status === 'processing' ? 
                    'animation: pulse 2s ease-in-out infinite;' : '';
                
                html += `
                    <div class="job-card ${statusClass}" style="${animationStyle}">
                        <div class="job-header">
                            <div class="job-title">${status.filename || 'PDF Document'}</div>
                            <div class="job-status status-${status.status}">${statusLabel}</div>
                        </div>
                        <div class="progress-text">${status.progress}%</div>
                        <div class="progress-bar-container">
                            <div class="progress-bar" style="width: ${status.progress}%"></div>
                        </div>
                        <div class="status-message">${status.message}</div>
                `;
                
                if (status.status === 'completed') {
                    html += `
                        <div style="margin-top: 20px; padding: 20px; background: #f0fff4; 
                             border-radius: 12px; border: 2px solid #9ae6b4;">
                            <strong style="color: #22543d; display: block; margin-bottom: 12px; font-size: 0.95em;">
                                Download Options:
                            </strong>
                            <div class="download-buttons" style="display: flex; flex-direction: column; gap: 10px;">
                                <a href="/download/${status.job_id}/package" class="btn btn-success" 
                                   style="text-align: center; margin: 0;" download>
                                    Complete Package (MD + Images ZIP)
                                </a>
                                <a href="/download/${status.job_id}/markdown" class="btn btn-info" 
                                   style="text-align: center; margin: 0;" download>
                                    Markdown Only
                                </a>
                            </div>
                        </div>
                    `;
                    
                    if (status.images && status.images.length > 0) {
                        html += `<div style="margin-top: 16px; padding: 18px; background: #fafafa; 
                                 border-radius: 12px; border: 2px solid #e2e8f0;">
                            <strong style="color: #2d3748; font-size: 0.9em;">
                                Intermediate Images (${status.images.length}):
                            </strong>
                            <div style="margin-top: 12px; display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px;">`;
                        status.images.forEach(img => {
                            html += `
                                <a href="/download/${status.job_id}/image/${img}" 
                                   style="display: block; padding: 10px 8px; 
                                   background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                   border-radius: 8px; text-decoration: none; 
                                   color: white; font-size: 0.7em; transition: all 0.3s ease;
                                   text-align: center; word-break: break-all;
                                   box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);"
                                   onmouseover="this.style.transform='translateY(-3px)'; this.style.boxShadow='0 6px 16px rgba(102,126,234,0.4)';"
                                   onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 8px rgba(102, 126, 234, 0.3)';"
                                   download>
                                    ${img}
                                </a>
                            `;
                        });
                        html += `</div></div>`;
                    }
                } else if (status.status === 'failed') {
                    html += `<div style="margin-top: 16px; padding: 16px; background: #fff5f5; 
                             border-radius: 10px; border: 2px solid #feb2b2; color: #742a2a;">
                        <strong style="display: block; margin-bottom: 6px;">Error:</strong> 
                        <span style="font-size: 0.9em;">${status.error || 'Unknown error occurred'}</span>
                    </div>`;
                }
                
                html += `</div>`;
            });
            
            jobList.innerHTML = html;
        }
        
        // Add CSS animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.8; }
            }
        `;
        document.head.appendChild(style);
    </script>
</body>
</html>
"""


def process_pdf_task(job_id, pdf_path, filename, api_key, base_url, model, gpt_worker, output_dir):
    """Background task to process PDF"""
    try:
        processing_status[job_id]['status'] = 'processing'
        processing_status[job_id]['message'] = 'Converting PDF to Markdown...'
        processing_status[job_id]['progress'] = 10
        processing_status[job_id]['filename'] = filename
        
        # Parse PDF
        kwargs = {
            'pdf_path': pdf_path,
            'output_dir': output_dir,
            'api_key': api_key,
            'model': model,
            'gpt_worker': gpt_worker
        }
        
        if base_url:
            kwargs['base_url'] = base_url
        
        processing_status[job_id]['progress'] = 30
        processing_status[job_id]['message'] = 'Parsing PDF pages...'
        
        content, image_paths = parse_pdf(**kwargs)
        
        processing_status[job_id]['progress'] = 90
        processing_status[job_id]['message'] = 'Finalizing...'
        
        # Store results
        processing_status[job_id]['status'] = 'completed'
        processing_status[job_id]['progress'] = 100
        processing_status[job_id]['message'] = 'Conversion complete!'
        processing_status[job_id]['images'] = image_paths
        processing_status[job_id]['output_dir'] = output_dir
        
    except Exception as e:
        processing_status[job_id]['status'] = 'failed'
        processing_status[job_id]['error'] = str(e)
        processing_status[job_id]['message'] = f'Error: {str(e)}'
        processing_status[job_id]['progress'] = 0


@app.route('/')
def index():
    """Main page"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/upload', methods=['POST'])
def upload_pdf():
    """Handle multiple PDF uploads and start parallel processing"""
    try:
        # Check if files are present
        if 'pdfs' not in request.files:
            return jsonify({'success': False, 'error': 'No PDF files provided'})
        
        pdf_files = request.files.getlist('pdfs')
        if not pdf_files or pdf_files[0].filename == '':
            return jsonify({'success': False, 'error': 'No files selected'})
        
        # Get parameters
        api_key = request.form.get('api_key')
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'})
        
        base_url = request.form.get('base_url', None)
        model = request.form.get('model', 'gpt-4o')
        gpt_worker = int(request.form.get('gpt_worker', 1))
        max_parallel = int(request.form.get('max_parallel', 3))
        
        job_ids = []
        
        # Process each PDF
        for pdf_file in pdf_files:
            if pdf_file.filename == '':
                continue
                
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            job_ids.append(job_id)
            
            # Save uploaded file
            filename = secure_filename(pdf_file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
            pdf_file.save(pdf_path)
            
            # Create output directory
            output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
            os.makedirs(output_dir, exist_ok=True)
            
            # Initialize status
            processing_status[job_id] = {
                'job_id': job_id,
                'status': 'queued',
                'progress': 0,
                'message': 'Queued...',
                'pdf_path': pdf_path,
                'filename': filename,
                'created_at': datetime.now().isoformat()
            }
            
            # Submit to thread pool
            pdf_executor.submit(
                process_pdf_task,
                job_id, pdf_path, filename, api_key, base_url, model, gpt_worker, output_dir
            )
        
        return jsonify({'success': True, 'job_ids': job_ids, 'count': len(job_ids)})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/status/<job_id>')
def get_status(job_id):
    """Get processing status"""
    if job_id not in processing_status:
        return jsonify({'status': 'not_found', 'error': 'Job not found'})
    
    status = processing_status[job_id]
    return jsonify(status)


@app.route('/status/batch', methods=['POST'])
def get_batch_status():
    """Get status for multiple jobs"""
    try:
        data = request.get_json()
        job_ids = data.get('job_ids', [])
        
        statuses = []
        for job_id in job_ids:
            if job_id in processing_status:
                statuses.append(processing_status[job_id])
        
        return jsonify(statuses)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/debug/jobs')
def debug_jobs():
    """Debug endpoint to see all jobs in memory"""
    jobs_info = {}
    for job_id, status in processing_status.items():
        jobs_info[job_id] = {
            'status': status.get('status'),
            'filename': status.get('filename'),
            'progress': status.get('progress'),
            'has_output_dir': 'output_dir' in status
        }
    return jsonify({
        'total_jobs': len(processing_status),
        'jobs': jobs_info
    })


@app.route('/download/<job_id>/markdown')
def download_markdown(job_id):
    """Download the generated markdown file"""
    if job_id not in processing_status:
        return "Job not found", 404
    
    status = processing_status[job_id]
    if status['status'] != 'completed':
        return "Job not completed", 400
    
    output_dir = status['output_dir']
    markdown_path = os.path.join(output_dir, 'output.md')
    
    if not os.path.exists(markdown_path):
        return "Markdown file not found", 404
    
    return send_file(markdown_path, as_attachment=True, download_name='output.md')


@app.route('/download/<job_id>/image/<image_name>')
def download_image(job_id, image_name):
    """Download an intermediate image"""
    if job_id not in processing_status:
        return "Job not found", 404
    
    status = processing_status[job_id]
    if status['status'] != 'completed':
        return "Job not completed", 400
    
    output_dir = status['output_dir']
    return send_from_directory(output_dir, image_name, as_attachment=True)


@app.route('/download/<job_id>/package')
def download_package(job_id):
    """Download complete package: MD + Images in organized ZIP"""
    if job_id not in processing_status:
        return "Job not found", 404
    
    status = processing_status[job_id]
    if status['status'] != 'completed':
        return "Job not completed", 400
    
    output_dir = status['output_dir']
    filename = status.get('filename', 'document').replace('.pdf', '')
    
    # Create a clean package structure
    package_dir = os.path.join(app.config['OUTPUT_FOLDER'], f"{job_id}_package")
    os.makedirs(package_dir, exist_ok=True)
    
    # Create subdirectories
    images_dir = os.path.join(package_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)
    
    # Copy markdown file
    markdown_src = os.path.join(output_dir, 'output.md')
    markdown_dst = os.path.join(package_dir, f'{filename}.md')
    if os.path.exists(markdown_src):
        shutil.copy2(markdown_src, markdown_dst)
    
    # Copy images
    if 'images' in status and status['images']:
        for img in status['images']:
            img_src = os.path.join(output_dir, img)
            img_dst = os.path.join(images_dir, img)
            if os.path.exists(img_src):
                shutil.copy2(img_src, img_dst)
    
    # Create ZIP file
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{job_id}_package")
    shutil.make_archive(zip_path, 'zip', package_dir)
    
    # Clean up temporary package directory
    shutil.rmtree(package_dir)
    
    return send_file(f"{zip_path}.zip", as_attachment=True, 
                     download_name=f'{filename}_complete.zip')


@app.route('/download/all')
def download_all_pdfs():
    """Download all completed PDFs as a single ZIP with organized structure"""
    try:
        job_ids = request.args.get('job_ids', '').split(',')
        if not job_ids or job_ids == ['']:
            return "No jobs specified", 400
        
        logging.info(f"Starting batch download for job_ids: {job_ids}")
        
        # Create main package directory
        batch_id = str(uuid.uuid4())[:8]
        batch_dir = os.path.join(app.config['OUTPUT_FOLDER'], f"batch_{batch_id}")
        os.makedirs(batch_dir, exist_ok=True)
        
        processed_count = 0
        for job_id in job_ids:
            job_id = job_id.strip()  # Remove any whitespace
            
            if not job_id:
                continue
            
            if job_id not in processing_status:
                logging.warning(f"Job '{job_id}' not found in processing_status. Available jobs: {list(processing_status.keys())}")
                continue
                
            status = processing_status[job_id]
            if status['status'] != 'completed':
                logging.warning(f"Job {job_id} status is '{status['status']}', not 'completed'")
                continue
            
            output_dir = status['output_dir']
            # Get clean filename without .pdf extension
            filename = status.get('filename', 'document').replace('.pdf', '').replace('.PDF', '')
            
            logging.info(f"Processing job {job_id}: {filename} from {output_dir}")
            
            # Ensure unique folder name by appending a counter if needed
            pdf_folder_name = filename
            counter = 1
            while os.path.exists(os.path.join(batch_dir, pdf_folder_name)):
                pdf_folder_name = f"{filename}_{counter}"
                counter += 1
            
            # Create PDF-specific folder
            pdf_folder = os.path.join(batch_dir, pdf_folder_name)
            os.makedirs(pdf_folder, exist_ok=True)
            
            # Create images subfolder
            images_folder = os.path.join(pdf_folder, 'images')
            os.makedirs(images_folder, exist_ok=True)
            
            # Copy markdown
            markdown_src = os.path.join(output_dir, 'output.md')
            markdown_dst = os.path.join(pdf_folder, f'{filename}.md')
            if os.path.exists(markdown_src):
                shutil.copy2(markdown_src, markdown_dst)
                processed_count += 1
                logging.info(f"Copied markdown for {filename}")
            else:
                logging.warning(f"Markdown not found: {markdown_src}")
            
            # Copy images
            if 'images' in status and status['images']:
                for img in status['images']:
                    img_src = os.path.join(output_dir, img)
                    img_dst = os.path.join(images_folder, img)
                    if os.path.exists(img_src):
                        shutil.copy2(img_src, img_dst)
                    else:
                        logging.warning(f"Image not found: {img_src}")
        
        # Check if we actually processed any PDFs
        if processed_count == 0:
            shutil.rmtree(batch_dir)
            logging.error("No completed PDFs found to download")
            return "No completed PDFs found to download", 404
        
        logging.info(f"Successfully processed {processed_count} PDFs, creating ZIP")
        
        # Create ZIP
        zip_path = os.path.join(app.config['OUTPUT_FOLDER'], f"all_pdfs_{batch_id}")
        shutil.make_archive(zip_path, 'zip', batch_dir)
        
        # Clean up temporary directory
        shutil.rmtree(batch_dir)
        
        logging.info(f"ZIP created successfully: {zip_path}.zip")
        
        return send_file(f"{zip_path}.zip", as_attachment=True, 
                         download_name=f'all_converted_pdfs_{processed_count}_files.zip')
        
    except Exception as e:
        return f"Error creating batch download: {str(e)}", 500


if __name__ == '__main__':
    print("=" * 60)
    print("PDF to Markdown Converter - Web UI")
    print("=" * 60)
    print("\nStarting server at: http://127.0.0.1:8080")
    print("\nFeatures:")
    print("   - Upload multiple PDF files")
    print("   - Parallel processing")
    print("   - Real-time progress tracking")
    print("   - Download markdown output")
    print("   - Download intermediate images")
    print("   - Download all files as ZIP")
    print("\nRequirements:")
    print("   - OpenAI API Key (required)")
    print("   - Internet connection")
    print("\n" + "=" * 60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=8080)
