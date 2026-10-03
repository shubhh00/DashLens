package com.dashlens.app.ui

import android.app.Application
import android.os.SystemClock
import android.view.SurfaceView
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.dashlens.app.config.ServerConfig
import com.dashlens.app.data.ConversationRepository
import com.dashlens.app.model.ConversationUiState
import com.dashlens.app.rtc.AgoraConversationSessionManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class ConversationViewModel(
    application: Application,
) : AndroidViewModel(application) {
    private val repository = ConversationRepository()
    private val sessionManager = AgoraConversationSessionManager(application)
    private val _uiState = MutableStateFlow(ConversationUiStateMapper.freshUiState())

    val uiState: StateFlow<ConversationUiState> = _uiState.asStateFlow()

    private var activeAgentId: String? = null

    init {
        viewModelScope.launch {
            sessionManager.snapshot.collectLatest { snapshot ->
                _uiState.update { current ->
                    ConversationUiStateMapper.mergeSession(current, snapshot)
                }
            }
        }
    }

    fun updateCameraPermission(granted: Boolean) {
        _uiState.update { it.copy(cameraPermissionGranted = granted) }
    }

    /** The agent sees the latest frame of the published camera track with every turn. */
    fun toggleCamera() {
        val enabled = !_uiState.value.cameraEnabled
        sessionManager.setCameraEnabled(enabled)
        _uiState.update { it.copy(cameraEnabled = enabled) }
    }

    /** Toggles 1x / 2x. 2x makes small cluster lamps legible to the agent. */
    fun toggleCameraZoom() {
        val zoom = if (_uiState.value.cameraZoom > 1f) 1f else 2f
        sessionManager.setCameraZoom(zoom)
        _uiState.update { it.copy(cameraZoom = zoom) }
    }

    fun bindCameraPreview(view: SurfaceView) = sessionManager.bindLocalPreview(view)

    fun unbindCameraPreview() = sessionManager.unbindLocalPreview()

    fun updateMicrophonePermission(granted: Boolean) {
        _uiState.update { it.copy(microphonePermissionGranted = granted) }
    }

    fun startConversation() {
        val currentState = _uiState.value
        if (currentState.isStarting || currentState.isStopping) {
            return
        }
        if (!ServerConfig.isConfigured) {
            _uiState.update {
                it.copy(
                    errorMessage = ServerConfig.startupHelpMessage(),
                    warningMessage = null,
                )
            }
            return
        }
        if (!currentState.microphonePermissionGranted) {
            _uiState.update {
                it.copy(
                    errorMessage = "Microphone access is required to publish your voice to the Agora channel.",
                    warningMessage = null,
                )
            }
            return
        }
        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isStarting = true,
                    errorMessage = null,
                    warningMessage = null,
                )
            }

            runCatching {
                val healthStartedAt = SystemClock.elapsedRealtime()
                val health = repository.checkHealth()
                _uiState.update {
                    it.copy(
                        backendLatencyMs = SystemClock.elapsedRealtime() - healthStartedAt,
                        lastServerResponse = "${health.status} (${health.version})",
                    )
                }
                val bootstrap = repository.requestSessionBootstrap()
                sessionManager.connect(bootstrap) { channel, rtcUid, rtmUserId ->
                    repository.renewTokens(
                        channel = channel,
                        rtcUid = rtcUid,
                        rtmUserId = rtmUserId,
                    )
                }

                val requesterRtcUid = sessionManager.snapshot.value.localRtcUid
                    .takeIf { it > 0 }
                    ?.toString()
                    ?: bootstrap.uid
                val inviteAttempt = runCatching {
                    repository.inviteAgent(
                        channelName = bootstrap.channel,
                        requesterRtcUid = requesterRtcUid,
                    )
                }
                val inviteResult = inviteAttempt.getOrNull()
                activeAgentId = inviteResult?.agentId
                sessionManager.setActiveAgentId(activeAgentId)

                val warning = inviteAttempt.exceptionOrNull()?.message?.let { message ->
                    "The Android client joined the channel, but the server could not start the Agora agent: $message"
                } ?: if (inviteResult?.agentId == null) {
                    "The Android client joined the channel, but the server returned no Agora agent ID."
                } else null

                _uiState.update { current ->
                    ConversationUiStateMapper.mergeSession(
                        current.copy(
                            isStarting = false,
                            inConversation = true,
                            warningMessage = warning,
                        ),
                        sessionManager.snapshot.value,
                    )
                }
            }.onFailure { error ->
                sessionManager.disconnect(resetSnapshot = true)
                activeAgentId = null
                _uiState.value = ConversationUiStateMapper.freshUiState(
                    permissionGranted = _uiState.value.microphonePermissionGranted,
                    errorMessage = error.message ?: "Unable to start the conversation through the DashLens server.",
                ).copy(lastServerResponse = "Request failed", cameraPermissionGranted = _uiState.value.cameraPermissionGranted)
            }
        }
    }

    fun endConversation() {
        val currentState = _uiState.value
        if (currentState.isStopping || currentState.isStarting) {
            return
        }

        // End locally first so the screen responds instantly; the server stops the cloud agent
        // (and saves the transcript) in the background.
        val agentId = activeAgentId
        val channelName = sessionManager.snapshot.value.channelName
        activeAgentId = null
        sessionManager.setActiveAgentId(null)
        sessionManager.disconnect(resetSnapshot = true)
        _uiState.value = ConversationUiStateMapper.freshUiState(
            permissionGranted = currentState.microphonePermissionGranted,
        ).copy(cameraPermissionGranted = currentState.cameraPermissionGranted)

        if (agentId != null && channelName != null) {
            viewModelScope.launch {
                runCatching { repository.stopConversation(agentId, channelName) }
                    .onFailure { error ->
                        // The idle timeout still stops the agent; only surface this if nothing new started.
                        if (activeAgentId == null) {
                            _uiState.update { it.copy(warningMessage = "The agent may take a moment to stop: ${error.message}") }
                        }
                    }
            }
        }
    }

    fun toggleMicrophone() {
        sessionManager.setMicrophoneEnabled(!_uiState.value.micRequestedEnabled)
    }

    fun clearTransientMessages() {
        _uiState.update {
            it.copy(
                errorMessage = null,
                warningMessage = null,
            )
        }
    }

    override fun onCleared() {
        // App closed mid-call (e.g. swiped away after opening the dialler): still tell the server, so
        // it saves the transcript and stops the agent instead of waiting for the idle timeout.
        val agentId = activeAgentId
        val channelName = sessionManager.snapshot.value.channelName
        if (agentId != null && channelName != null) {
            CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
                runCatching { repository.stopConversation(agentId, channelName) }
            }
        }
        sessionManager.release()
        super.onCleared()
    }
}
