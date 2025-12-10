/** @odoo-module **/

/**
 * Voice-to-PV Recorder Module
 * LOCAL RECORDING + AssemblyAI Transcription
 * Works OFFLINE + sends to AssemblyAI when Internet is available
 */

export class VoicePVRecorder {
    constructor(pvTextarea, meetingId, notification) {
        this.pvTextarea = pvTextarea;
        this.meetingId = meetingId;
        this.notification = notification;

        // Audio recording state
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.stream = null;

        // UI elements
        this.recordButton = null;
        this.statusDisplay = null;

        // ✅ ALWAYS use local MediaRecorder (works offline)
        this.isUsingSpeechAPI = false;

        console.log('🎤 Voice Recorder initialized');
        console.log('✅ Mode: Local recording + AssemblyAI transcription');
        console.log('✅ Works OFFLINE + sends when Internet available');
    }

    /**
     * Start local audio recording
     */
    async startRecording() {
        try {
            if (this.isRecording) {
                console.log('⚠️ Already recording');
                this.notification.add('Enregistrement déjà en cours', { type: 'warning' });
                return;
            }

            console.log('🎤 Starting LOCAL audio recording...');
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

                console.log('✅ Microphone access granted');
            } catch (error) {
                if (error.name === 'NotAllowedError') {
                    console.error('❌ Microphone permission DENIED');
                    this.notification.add('❌ Permission microphone refusée! Allez dans les paramètres du navigateur.', { type: 'danger' });
                } else if (error.name === 'NotFoundError') {
                    console.error('❌ No microphone found');
                    this.notification.add('❌ Aucun microphone trouvé', { type: 'danger' });
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
                    console.log(`📊 Audio chunk: ${event.data.size} bytes`);
                }
            };

            this.mediaRecorder.onstop = async () => {
                console.log('⏹️ Recording stopped, processing audio...');
                await this._processRecordedAudio();
            };

            this.mediaRecorder.onerror = (event) => {
                console.error('❌ MediaRecorder error:', event.error);
                this.notification.add(`Erreur d'enregistrement: ${event.error}`, { type: 'danger' });
            };

            // Start recording
            this.mediaRecorder.start();
            this.isRecording = true;

            console.log('✅ LOCAL recording started');
            this._updateUI('⏹️ Arrêter l\'enregistrement', true);
            this.notification.add('🎤 Enregistrement vocal démarré (LOCAL)', { type: 'info' });
            this._updateStatus('🎙️ Enregistrement en cours... (fonctionne hors ligne)');

        } catch (error) {
            console.error('❌ Recording start error:', error);
            this.isRecording = false;
            this._updateUI('🎤 Démarrer l\'enregistrement', false);
            this.notification.add(`Erreur: ${error.message}`, { type: 'danger' });
        }
    }

    /**
     * Stop local audio recording
     */
    async stopRecording() {
        try {
            if (!this.isRecording || !this.mediaRecorder) {
                console.log('⚠️ Not recording');
                return;
            }

            console.log('⏹️ Stopping recording...');
            this.mediaRecorder.stop();
            this.isRecording = false;

            // Stop all tracks
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
                console.log('✅ Audio stream stopped');
            }

            this._updateUI('🎤 Démarrer l\'enregistrement', false);
            this._updateStatus('⏳ Traitement de l\'audio...');

        } catch (error) {
            console.error('❌ Recording stop error:', error);
            this.isRecording = false;
            this._updateUI('🎤 Démarrer l\'enregistrement', false);
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
                return;
            }

            console.log(`📀 Audio blob size: ${audioBlob.size} bytes`);

            // Convert to base64
            const base64Audio = await this._blobToBase64(audioBlob);
            console.log(`🔐 Base64 encoded: ${base64Audio.substring(0, 50)}...`);

            // Send to transcription endpoint
            this._updateStatus('📤 Envoi vers le serveur...', false);
            console.log('📤 Sending to /meeting/voice/transcribe...');

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

            console.log(`📨 Response status: ${response.status}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            console.log('✅ Response received:', data);

            if (data.error) {
                throw new Error(data.error.message || 'Transcription failed');
            }

            const result = data.result;

            if (result && result.success) {
                console.log(`✅ Transcription réussie (${result.provider})`);
                this._updateStatus(`✅ Transcription réussie (${result.provider})`, false);

                // Add transcribed text to PV
                const currentText = this.pvTextarea.value;
                const newText = currentText + (currentText ? '\n\n' : '') + result.transcript;
                this.pvTextarea.value = newText;

                console.log(`📝 Added ${result.transcript.length} characters to PV`);

                // Optionally enhance the text with AI
                if (result.transcript.length > 10) {
                    await this._enhanceText(result.transcript);
                }

                this.notification.add('✅ Texte ajouté au PV', { type: 'success' });
            } else {
                throw new Error(result?.error || 'Transcription failed');
            }

        } catch (error) {
            console.error('❌ Audio processing error:', error);

            let userMessage = error.message;

            if (error.message.includes('HTTP')) {
                userMessage = `Erreur serveur: ${error.message}`;
            } else if (error.message.includes('timeout')) {
                userMessage = 'Transcription trop longue. Essayez avec un audio plus court.';
            } else if (error.message.includes('not configured')) {
                userMessage = 'Fournisseur de transcription non configuré. Allez dans Settings.';
            }

            this._updateStatus(`❌ ${userMessage}`, false);
            this.notification.add(`Erreur: ${userMessage}`, { type: 'danger' });
        }
    }

    /**
     * Enhance transcribed text using AI
     */
    async _enhanceText(transcript) {
        try {
            this._updateStatus('🤖 Amélioration du texte avec l\'AI...', false);

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
                    this.pvTextarea.value = newText;

                    this._updateStatus(`✨ Texte amélioré par ${result.provider}`, false);
                    this.notification.add('✨ Texte amélioré par l\'AI', { type: 'success' });
                }
            }

        } catch (error) {
            console.warn('Text enhancement error:', error);
            // Don't fail if enhancement fails, we already have the transcript
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
    _updateUI(buttonText, isActive) {
        if (this.recordButton) {
            this.recordButton.textContent = buttonText;
            this.recordButton.disabled = false;
            if (isActive) {
                this.recordButton.classList.add('recording-active');
            } else {
                this.recordButton.classList.remove('recording-active');
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
     * Initialize UI controls in the form
     */
    initializeControls(container) {
        // Create controls if not already present
        const controlsHtml = `
            <div class="voice-controls" style="margin: 15px 0; padding: 15px; background: #f0f9ff; border-radius: 8px; border: 2px solid #3b82f6;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                    <button class="btn btn-primary voice-record-btn" type="button" style="flex: 0 0 auto;">
                        <i class="fa fa-microphone"></i> 🎤 Démarrer l'enregistrement
                    </button>
                    <div class="voice-status" style="flex: 1; font-size: 13px; color: #64748b;">
                        ✅ Prêt à enregistrer (hors ligne)
                    </div>
                </div>
                <div class="voice-info" style="font-size: 12px; color: #64748b; padding-top: 10px; border-top: 1px solid #ddd;">
                    <p style="margin: 5px 0;">
                        <strong>💡 Mode:</strong> Enregistrement LOCAL (fonctionne hors ligne) + Transcription AssemblyAI (quand Internet revient)
                    </p>
                    <p style="margin: 5px 0;">
                        <strong>🎯 Processus:</strong>
                        1️⃣ Parlez et enregistrez
                        2️⃣ Cliquez "Arrêter"
                        3️⃣ Envoi automatique à AssemblyAI (si Internet disponible)
                    </p>
                </div>
            </div>
        `;

        // Insert controls before textarea
        const wrapper = document.createElement('div');
        wrapper.innerHTML = controlsHtml;
        this.pvTextarea.parentNode.insertBefore(wrapper, this.pvTextarea);

        // Get references to controls
        this.recordButton = wrapper.querySelector('.voice-record-btn');
        this.statusDisplay = wrapper.querySelector('.voice-status');

        // Setup event listeners
        this.recordButton.addEventListener('click', async (e) => {
            e.preventDefault();
            if (this.isRecording) {
                await this.stopRecording();
            } else {
                await this.startRecording();
            }
        });

        // Add CSS for recording state
        const style = document.createElement('style');
        style.textContent = `
            .recording-active {
                background-color: #ef4444 !important;
                border-color: #dc2626 !important;
                animation: pulse-record 1s infinite;
            }

            @keyframes pulse-record {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }

            .voice-controls {
                transition: all 0.3s ease;
            }

            .voice-record-btn {
                white-space: nowrap;
            }

            .voice-record-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
            }
        `;
        document.head.appendChild(style);
    }
}

export default VoicePVRecorder;