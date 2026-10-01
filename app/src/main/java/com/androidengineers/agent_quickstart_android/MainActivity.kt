package com.androidengineers.agent_quickstart_android

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.androidengineers.agent_quickstart_android.ui.ClusterScreen
import com.androidengineers.agent_quickstart_android.ui.ConversationViewModel
import com.androidengineers.agent_quickstart_android.ui.theme.AgentquickstartandroidTheme

class MainActivity : ComponentActivity() {
    private val viewModel by viewModels<ConversationViewModel>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The Cluster Agent design is dark-only.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )

        setContent {
            val uiState by viewModel.uiState.collectAsStateWithLifecycle()

            AgentquickstartandroidTheme(darkTheme = true) {
                val context = LocalContext.current
                val currentViewModel by rememberUpdatedState(viewModel)
                fun granted(permission: String) =
                    ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

                val micPermissionLauncher = rememberLauncherForActivityResult(
                    contract = ActivityResultContracts.RequestPermission()
                ) { isGranted ->
                    currentViewModel.updateMicrophonePermission(isGranted)
                    if (isGranted) currentViewModel.startConversation()
                }
                val cameraPermissionLauncher = rememberLauncherForActivityResult(
                    contract = ActivityResultContracts.RequestPermission()
                ) { isGranted ->
                    currentViewModel.updateCameraPermission(isGranted)
                }

                LaunchedEffect(Unit) {
                    currentViewModel.updateMicrophonePermission(granted(Manifest.permission.RECORD_AUDIO))
                    val camera = granted(Manifest.permission.CAMERA)
                    currentViewModel.updateCameraPermission(camera)
                    // The agent's view of the dashboard is the camera, so ask up front.
                    if (!camera) cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                }

                ClusterScreen(
                    uiState = uiState,
                    onStart = {
                        val mic = granted(Manifest.permission.RECORD_AUDIO)
                        currentViewModel.updateMicrophonePermission(mic)
                        if (mic) currentViewModel.startConversation()
                        else micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    },
                    onEnd = viewModel::endConversation,
                    onToggleMicrophone = viewModel::toggleMicrophone,
                    onToggleCamera = viewModel::toggleCamera,
                    onToggleZoom = viewModel::toggleCameraZoom,
                    onRequestCameraPermission = { cameraPermissionLauncher.launch(Manifest.permission.CAMERA) },
                    onBindPreview = viewModel::bindCameraPreview,
                    onUnbindPreview = viewModel::unbindCameraPreview,
                    onDismissMessages = viewModel::clearTransientMessages,
                )
            }
        }
    }
}
