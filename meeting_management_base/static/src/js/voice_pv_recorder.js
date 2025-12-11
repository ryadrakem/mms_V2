/** @odoo-module **/

/**
 * Voice-to-PV Recorder Module
 * LOCAL RECORDING + AssemblyAI Transcription
 * Works OFFLINE + sends to AssemblyAI when Internet is available
 * Supports multiple recordings with separators
 */

export class VoicePVRecorder {
    constructor(pvTextarea, meetingId, notification, onTextUpdate = null) {
        this.pvTextarea = pvTextarea;
        this.meetingId = meetingId;
        this.notification = notification;
        this.onTextUpdate = onTextUpdate; // Callback for Owl state update

        // Audio recording state
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.stream = null;
        this.recordingCount = 0; // Compter les enregistrements

        // UI elements - will be set in initializeControls
        this.recordButton = null;
        this.statusDisplay = null;
        this.addSeparatorBtn = null;

        // ✓ ALWAYS use local MediaRecorder (works offline)
        this.isUsingSpeechAPI = false;

        console.log('✓ Voice Recorder initialized');
        console.log('✓ Mode: Local recording + AssemblyAI transcription');
        console.log('✓ Works OFFLINE + sends when Internet available');
        console.log('✓ Multiple recordings supported');
    }

    /**
     * Update text in both textarea and Owl state
     */
    _updatePVText(newText) {
        // Update DOM
        this.pvTextarea.value = newText;

        // Update Owl state via callback
        if (this.onTextUpdate && typeof this.onTextUpdate === 'function') {
            this.onTextUpdate(newText);
        }
    }

    /**
     * Add a separator between recordings
     */
    addSeparator() {
        const currentText = this.pvTextarea.value;
        const separator = '\n\n' + '─'.repeat(60) + '\n\n';
        const newText = currentText ? currentText + separator : '';

        this._updatePVText(newText);
        this.notification.add('✓ Séparateur ajouté', { type: 'info' });
        console.log('✓ Separator added');
    }

    /**
     * Start local audio recording
     */
    async startRecording() {
        try {
            if (this.isRecording) {
                console.log('Already recording');
                this.notification.add('Enregistrement déjà en cours', { type: 'warning' });
                return;
            }

            console.log('✓ Starting audio recording...');
            this.audioChunks = [];

            // Request microphone access
            try {
                this.stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });

                console.log('✓ Microphone access granted');
            } catch (error) {
                if (error.name === 'NotAllowedError') {
                    console.error('✗ Microphone permission DENIED');
                    this.notification.add('✗ Permission microphone refusée! Allez dans les paramètres du navigateur.', { type: 'danger' });
                } else if (error.name === 'NotFoundError') {
                    console.error('✗ No microphone found');
                    this.notification.add('✗ Aucun microphone trouvé', { type: 'danger' });
                } else {
                    throw error;
                }
                return;
            }

            // Create MediaRecorder
            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: 'audio/webm'
            });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                    console.log(`🎙 Audio chunk: ${event.data.size} bytes`);
                }
            };

            this.mediaRecorder.onstop = async () => {
                console.log('⏹ Recording stopped, processing audio...');
                await this._processRecordedAudio();
            };

            this.mediaRecorder.onerror = (event) => {
                console.error('✗ MediaRecorder error:', event.error);
                this.notification.add(`Erreur d'enregistrement: ${event.error}`, { type: 'danger' });
            };

            // Start recording
            this.mediaRecorder.start();
            this.isRecording = true;

            console.log('✓ recording started');
            this._updateUI(true);
            this.notification.add('✓ Enregistrement vocal démarré (LOCAL)', { type: 'info' });
            this._updateStatus('🎙 Enregistrement en cours... (fonctionne hors ligne)');

        } catch (error) {
            console.error('✗ Recording start error:', error);
            this.isRecording = false;
            this._updateUI(false);
            this.notification.add(`Erreur: ${error.message}`, { type: 'danger' });
        }
    }

    /**
     * Stop local audio recording
     */
    async stopRecording() {
        try {
            if (!this.isRecording || !this.mediaRecorder) {
                console.log('⏸ Not recording');
                return;
            }

            console.log('⏹ Stopping recording...');
            this.mediaRecorder.stop();
            this.isRecording = false;

            // Stop all tracks
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
                console.log('✓ Audio stream stopped');
            }

            this._updateUI(false);
            this._updateStatus('⏳ Traitement de l\'audio...');

        } catch (error) {
            console.error('✗ Recording stop error:', error);
            this.isRecording = false;
            this._updateUI(false);
            this.notification.add(`Erreur: ${error.message}`, { type: 'danger' });
        }
    }

    /**
     * Process recorded audio and send to transcription API
     */
    async _processRecordedAudio() {
        try {
            // Show processing status
            this._updateStatus('⏳ Traitement de l\'audio...', false);

            // Convert audio chunks to blob
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });

            if (audioBlob.size === 0) {
                this.notification.add('Aucun audio enregistré', { type: 'warning' });
                this._updateStatus('✓ Prêt à enregistrer (hors ligne)');
                return;
            }

            console.log(`🎙 Audio blob size: ${audioBlob.size} bytes`);

            // Convert to base64
            const base64Audio = await this._blobToBase64(audioBlob);
            console.log(`🎙 Base64 encoded: ${base64Audio.substring(0, 50)}...`);

            // Send to transcription endpoint
            this._updateStatus('🎙🤖 Envoi vers le serveur...', false);
            console.log('🎙🤖 Sending to /meeting/voice/transcribe...');

            const response = await fetch('/meeting/voice/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        audio_data: base64Audio,
                        meeting_id: this.meetingId,
                        format: 'webm'
                    }
                })
            });

            console.log(`🎙🨘 Response status: ${response.status}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            console.log('✓ Response received:', data);

            if (data.error) {
                throw new Error(data.error.message || 'Transcription failed');
            }

            const result = data.result;

            if (result && result.success) {
                this.recordingCount++;
                console.log(`✓ Transcription réussie (${result.provider})`);
                this._updateStatus(`✓ Transcription #${this.recordingCount} réussie (${result.provider})`, false);

                // Add transcribed text to PV (update both DOM and state)
                const currentText = this.pvTextarea.value;
                const newText = currentText + (currentText ? '\n\n' : '') + result.transcript;
                this._updatePVText(newText);

                console.log(`" Added ${result.transcript.length} characters to PV`);

                // Optionally enhance the text with AI
                if (result.transcript.length > 10) {
                    await this._enhanceText(result.transcript);
                }

                this.notification.add(`✓ Texte #${this.recordingCount} ajouté au PV`, { type: 'success' });
                this._updateStatus('✓ Prêt à enregistrer à nouveau', false);
            } else {
                throw new Error(result?.error || 'Transcription failed');
            }

        } catch (error) {
            console.error('✓ Audio processing error:', error);

            let userMessage = error.message;

            if (error.message.includes('HTTP')) {
                userMessage = `Erreur serveur: ${error.message}`;
            } else if (error.message.includes('timeout')) {
                userMessage = 'Transcription trop longue. Essayez avec un audio plus court.';
            } else if (error.message.includes('not configured')) {
                userMessage = 'Fournisseur de transcription non configuré. Allez dans Settings.';
            }

            this._updateStatus(`✗ ${userMessage}`, false);
            this.notification.add(`Erreur: ${userMessage}`, { type: 'danger' });
        }
    }

    /**
     * Enhance transcribed text using AI
     */
    async _enhanceText(transcript) {
        try {
            this._updateStatus('💬 Amélioration du texte avec l\'AI...', false);

            const response = await fetch('/meeting/voice/enhance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        transcript: transcript,
                        meeting_id: this.meetingId
                    }
                })
            });

            const data = await response.json();

            if (data.error) {
                console.warn('Enhancement failed, using original text');
                return;
            }

            const result = data.result;

            if (result.success) {
                // Replace the added text with enhanced version
                const currentText = this.pvTextarea.value;
                const enhancedText = result.enhanced_text;

                // Find and replace the last added transcript
                const lastIndex = currentText.lastIndexOf(transcript);
                if (lastIndex !== -1) {
                    const newText = currentText.substring(0, lastIndex) +
                                   enhancedText +
                                   currentText.substring(lastIndex + transcript.length);
                    this._updatePVText(newText);

                    this._updateStatus(`💨 Texte amélioré par ${result.provider}`, false);
                    this.notification.add('💨 Texte amélioré par l\'AI', { type: 'success' });
                }
            }

        } catch (error) {
            console.warn('Text enhancement error:', error);
        }
    }

    /**
     * Convert blob to base64
     */
    _blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    /**
     * Update UI button state
     */
    _updateUI(isActive) {
        if (this.recordButton) {
            if (isActive) {
                this.recordButton.classList.add('recording-active');
                this.recordButton.style.animation = 'pulse-record 1s infinite';
            } else {
                this.recordButton.classList.remove('recording-active');
                this.recordButton.style.animation = 'none';
            }
        }
    }

    /**
     * Update status display
     */
    _updateStatus(message, isRecording = null) {
        if (this.statusDisplay) {
            this.statusDisplay.textContent = message;
            this.statusDisplay.style.display = 'block';
        }
        console.log(`[Voice Recorder] ${message}`);
    }

    /**
     * Initialize UI controls using existing DOM elements
     */
    initializeControls(container) {
        const parentSection = this.pvTextarea.closest('.main-tab-content');

        if (parentSection) {
            this.recordButton = parentSection.querySelector('.voice-record-btn');
            this.statusDisplay = parentSection.querySelector('.voice-status');
            this.addSeparatorBtn = parentSection.querySelector('.voice-add-separator-btn');
        }

        if (!this.recordButton) {
            console.warn('⚠️ Voice record button not found in DOM');
            return;
        }

        // Setup event listener on the main record button
        this.recordButton.addEventListener('click', async (e) => {
            e.preventDefault();
            if (this.isRecording) {
                await this.stopRecording();
            } else {
                await this.startRecording();
            }
        });

        // Setup event listener on the separator button
        if (this.addSeparatorBtn) {
            this.addSeparatorBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.addSeparator();
            });
        }

        // Add CSS for recording state animation if not already added
        if (!document.getElementById('voice-recorder-styles')) {
            const style = document.createElement('style');
            style.id = 'voice-recorder-styles';
            style.textContent = `
                .recording-active {
                    background-color: #ef4444 !important;
                    border-color: #dc2626 !important;
                }

                @keyframes pulse-record {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.7; }
                }

                .voice-record-btn {
                    white-space: nowrap;
                    transition: all 0.3s ease;
                }

                .voice-record-btn:hover:not(.recording-active) {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
                }

                .voice-add-separator-btn {
                    white-space: nowrap;
                    transition: all 0.3s ease;
                }

                .voice-add-separator-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(168, 85, 247, 0.4);
                }

                .voice-status {
                    animation: slide-in 0.3s ease;
                    font-size: 0.85rem;
                    color: #666;
                    margin-top: 8px;
                }

                @keyframes slide-in {
                    from {
                        opacity: 0;
                        transform: translateY(-10px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }
            `;
            document.head.appendChild(style);
        }

        console.log('✅ Voice recorder controls initialized');
        this._updateStatus('✅ Prêt à enregistrer (hors ligne)');
    }
}

export default VoicePVRecorder;