package com.androidengineers.agent_quickstart_android.ui

import android.view.SurfaceView
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.VideocamOff
import androidx.compose.material.icons.outlined.CenterFocusWeak
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.androidengineers.agent_quickstart_android.R
import com.androidengineers.agent_quickstart_android.audio.TurnState
import com.androidengineers.agent_quickstart_android.model.AgentVisualState
import com.androidengineers.agent_quickstart_android.model.ConversationUiState
import com.androidengineers.agent_quickstart_android.model.TranscriptSpeaker
import kotlinx.coroutines.delay

// DashLens palette: dark cluster, amber accent (from the design).
private val Bg = Color(0xFF0E1012)
private val CardTop = Color(0xFF1B1E23)
private val CardBottom = Color(0xFF14161A)
private val Hairline = Color(0xFF262A30)
private val TextPrimary = Color(0xFFF2F3F5)
private val TextMuted = Color(0xFF8E949B)
private val TextFaint = Color(0xFF5C6168)
private val Amber = Color(0xFFF5A623)
private val Green = Color(0xFF34C759)
private val Red = Color(0xFFE5484D)

private val Grotesk = FontFamily(
    Font(R.font.space_grotesk_medium, FontWeight.Medium),
    Font(R.font.space_grotesk_bold, FontWeight.Bold),
)
private val Inter = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
)
private val Label = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Medium, fontSize = 11.sp, letterSpacing = 1.6.sp, color = TextFaint)
private val Body = TextStyle(fontFamily = Inter, fontSize = 14.sp, color = TextMuted)

private const val DEFAULT_AGENT_LINE = "Show me the dashboard and tell me what's bothering you."

@Composable
fun ClusterScreen(
    uiState: ConversationUiState,
    onStart: () -> Unit,
    onEnd: () -> Unit,
    onToggleMicrophone: () -> Unit,
    onToggleCamera: () -> Unit,
    onToggleZoom: () -> Unit,
    onRequestCameraPermission: () -> Unit,
    onBindPreview: (SurfaceView) -> Unit,
    onUnbindPreview: () -> Unit,
    onDismissMessages: () -> Unit,
) {
    val agentLine = uiState.latestLine(TranscriptSpeaker.AGENT) ?: DEFAULT_AGENT_LINE
    val userLine = uiState.latestLine(TranscriptSpeaker.USER)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Bg)
            .safeDrawingPadding()
            .padding(horizontal = 20.dp)
            .padding(top = 8.dp, bottom = 12.dp),
    ) {
        Header(uiState)
        Spacer(Modifier.height(18.dp))

        CameraCard(
            uiState = uiState,
            onRequestCameraPermission = onRequestCameraPermission,
            onToggleZoom = onToggleZoom,
            onBindPreview = onBindPreview,
            onUnbindPreview = onUnbindPreview,
            modifier = Modifier.weight(1f).fillMaxWidth(),
        )

        Spacer(Modifier.height(22.dp))
        if (userLine != null) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
                Text(
                    text = userLine,
                    style = Body.copy(color = TextPrimary, fontSize = 14.sp),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier
                        .widthIn(max = 280.dp)
                        .clip(RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp, bottomStart = 16.dp, bottomEnd = 4.dp))
                        .background(CardTop)
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                )
            }
            Spacer(Modifier.height(14.dp))
        }

        AgentLabel(speaking = uiState.agentVisualState == AgentVisualState.SPEAKING && uiState.inConversation)
        Spacer(Modifier.height(8.dp))
        Box(Modifier.fillMaxWidth().heightIn(min = 60.dp)) {
            AgentCaption(
                full = agentLine,
                speaking = uiState.agentVisualState == AgentVisualState.SPEAKING,
                live = uiState.inConversation,
            )
        }

        val message = uiState.errorMessage ?: uiState.warningMessage
        if (message != null) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = message,
                style = Body.copy(fontSize = 13.sp, color = if (uiState.errorMessage != null) Red else Amber),
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.clickable(onClick = onDismissMessages),
            )
        }

        Spacer(Modifier.height(18.dp))
        if (uiState.inConversation) {
            ConversationControls(uiState, onEnd, onToggleMicrophone, onToggleCamera)
        } else {
            StartControls(uiState, onStart)
        }
    }
}

@Composable
private fun Header(uiState: ConversationUiState) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().height(40.dp)) {
        LensMark(Modifier.size(28.dp))
        Spacer(Modifier.width(10.dp))
        Text("DashLens", fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = TextPrimary)
        Spacer(Modifier.weight(1f))
        if (uiState.inConversation) {
            val (label, color) = when (uiState.agentVisualState) {
                AgentVisualState.LISTENING -> "Listening" to Green
                AgentVisualState.SPEAKING -> "Speaking" to Amber
                AgentVisualState.THINKING -> "Thinking" to Amber
                AgentVisualState.WAITING -> "Connecting" to TextMuted
                AgentVisualState.IDLE -> "Ready" to Green
                AgentVisualState.DISCONNECTED -> "Offline" to Red
            }
            StatusPill(label = label, color = color, pulse = uiState.agentVisualState != AgentVisualState.IDLE)
        } else {
            StatusPill(label = "No car yet", color = TextFaint, pulse = false)
        }
    }
}

/** The DashLens mark: one cluster gauge with an amber warning lamp (same drawing as the launcher icon). */
@Composable
private fun LensMark(modifier: Modifier = Modifier) {
    Canvas(modifier) {
        // Icon coordinates span roughly 28..80 on both axes; map that 52-unit box onto the canvas.
        val u = size.minDimension / 52f
        fun p(x: Float, y: Float) = Offset((x - 28f) * u, (y - 26f) * u)
        drawArc(
            color = TextPrimary,
            startAngle = 135f,
            sweepAngle = 270f,
            useCenter = false,
            topLeft = p(29.5f, 27.5f),
            size = Size(49f * u, 49f * u),
            style = Stroke(width = 5f * u, cap = StrokeCap.Round),
        )
        listOf(
            p(37f, 52f) to p(33.5f, 52f), p(42.33f, 40.33f) to p(39.85f, 37.85f), p(54f, 35f) to p(54f, 31.5f),
            p(65.67f, 40.33f) to p(68.15f, 37.85f), p(71f, 52f) to p(74.5f, 52f),
        ).forEach { (a, b) -> drawLine(TextPrimary, a, b, 2.6f * u, StrokeCap.Round) }
        drawLine(Amber, p(54f, 52f), p(64.6f, 41.4f), 4.2f * u, StrokeCap.Round)
        drawCircle(TextPrimary, radius = 3.6f * u, center = p(54f, 52f))
        val lamp = Path().apply {
            val t = p(54f, 62f); val r = p(61.5f, 75f); val l = p(46.5f, 75f)
            moveTo(t.x, t.y); lineTo(r.x, r.y); lineTo(l.x, l.y); close()
        }
        drawPath(lamp, Amber)
        drawPath(lamp, Amber, style = Stroke(width = 2.4f * u, join = StrokeJoin.Round))
        drawLine(Bg, p(54f, 66.3f), p(54f, 70.4f), 2.2f * u, StrokeCap.Round)
        drawCircle(Bg, radius = 1.2f * u, center = p(54f, 72.9f))
    }
}

@Composable
private fun StatusPill(label: String, color: Color, pulse: Boolean) {
    val animatedColor by animateColorAsState(color, label = "pill")
    val alpha = if (pulse) {
        val transition = rememberInfiniteTransition(label = "pill-pulse")
        transition.animateFloat(1f, 0.35f, infiniteRepeatable(tween(900, easing = LinearEasing), RepeatMode.Reverse), label = "dot").value
    } else 1f
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .border(BorderStroke(1.dp, animatedColor.copy(alpha = 0.45f)), RoundedCornerShape(50))
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(animatedColor.copy(alpha = alpha)))
        Spacer(Modifier.width(7.dp))
        Text(label, fontFamily = Inter, fontWeight = FontWeight.Medium, fontSize = 12.sp, color = animatedColor)
    }
}

@Composable
private fun AgentLabel(speaking: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("AGENT", style = Label)
        if (speaking) {
            Spacer(Modifier.width(8.dp))
            SpeakingBars()
        }
    }
}

/** Three small amber bars that bounce while the agent talks. */
@Composable
private fun SpeakingBars() {
    val transition = rememberInfiniteTransition(label = "bars")
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        listOf(0, 150, 300).forEach { offset ->
            val h by transition.animateFloat(
                initialValue = 3f,
                targetValue = 10f,
                animationSpec = infiniteRepeatable(tween(420, delayMillis = offset, easing = LinearEasing), RepeatMode.Reverse),
                label = "bar$offset",
            )
            Box(Modifier.width(2.5.dp).height(h.dp).clip(RoundedCornerShape(2.dp)).background(Amber))
        }
    }
}

@Composable
private fun CameraCard(
    uiState: ConversationUiState,
    onRequestCameraPermission: () -> Unit,
    onToggleZoom: () -> Unit,
    onBindPreview: (SurfaceView) -> Unit,
    onUnbindPreview: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val live = uiState.cameraPermissionGranted && uiState.inConversation
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(24.dp))
            .background(Brush.verticalGradient(listOf(CardTop, CardBottom)))
            .border(BorderStroke(1.dp, Hairline), RoundedCornerShape(24.dp)),
    ) {
        if (live) {
            // Agora renders the published rear-camera track here; the agent sees these frames.
            AndroidView(
                factory = { ctx -> SurfaceView(ctx).also(onBindPreview) },
                onRelease = { onUnbindPreview() },
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp)
                    .clickable(enabled = !uiState.cameraPermissionGranted, onClick = onRequestCameraPermission),
            ) {
                Icon(Icons.Outlined.CenterFocusWeak, contentDescription = null, tint = Amber.copy(alpha = 0.85f), modifier = Modifier.size(44.dp))
                Spacer(Modifier.height(18.dp))
                Text(
                    "Point your phone at the\ninstrument cluster",
                    fontFamily = Grotesk,
                    fontWeight = FontWeight.Medium,
                    fontSize = 18.sp,
                    lineHeight = 24.sp,
                    color = TextPrimary,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    if (uiState.cameraPermissionGranted) "DashLens reads the warning lights with you" else "Tap to allow camera access",
                    style = Body.copy(fontSize = 13.sp),
                    textAlign = TextAlign.Center,
                )
            }
        }

        if (live && !uiState.cameraEnabled) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
                modifier = Modifier.fillMaxSize().background(Bg.copy(alpha = 0.85f)),
            ) {
                Icon(Icons.Filled.VideocamOff, contentDescription = null, tint = TextMuted, modifier = Modifier.size(36.dp))
                Spacer(Modifier.height(12.dp))
                Text("Camera paused", fontFamily = Grotesk, fontWeight = FontWeight.Medium, fontSize = 17.sp, color = TextPrimary)
                Spacer(Modifier.height(4.dp))
                Text("The agent can't see the dashboard", style = Body.copy(fontSize = 13.sp))
            }
        }

        ViewfinderCorners(color = if (live && uiState.cameraEnabled) Color.White.copy(alpha = 0.55f) else TextFaint, modifier = Modifier.fillMaxSize().padding(14.dp))

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.align(Alignment.TopStart).padding(start = 22.dp, top = 20.dp),
        ) {
            if (live && uiState.cameraEnabled) {
                Box(Modifier.size(6.dp).clip(CircleShape).background(Red))
                Spacer(Modifier.width(6.dp))
            }
            Text(
                when {
                    !live -> "CAMERA"
                    uiState.cameraEnabled -> "LIVE"
                    else -> "PAUSED"
                },
                style = Label.copy(color = if (live && uiState.cameraEnabled) TextPrimary else TextFaint),
            )
        }

        if (live) {
            Surface(
                onClick = onToggleZoom,
                shape = RoundedCornerShape(50),
                color = Bg.copy(alpha = 0.65f),
                border = BorderStroke(1.dp, if (uiState.cameraZoom > 1f) Amber else Hairline),
                modifier = Modifier.align(Alignment.TopEnd).padding(top = 12.dp, end = 12.dp),
            ) {
                Text(
                    if (uiState.cameraZoom > 1f) "2×" else "1×",
                    fontFamily = Inter,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 13.sp,
                    color = if (uiState.cameraZoom > 1f) Amber else TextPrimary,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                )
            }
            CameraHint(uiState, Modifier.align(Alignment.BottomCenter).padding(bottom = 16.dp))
        }
    }
}

/**
 * Agora attaches the latest camera frame to the turn when the driver stops speaking, so: ask them
 * to hold steady while they talk, then confirm the frame went out.
 */
@Composable
private fun CameraHint(uiState: ConversationUiState, modifier: Modifier = Modifier) {
    if (!uiState.cameraEnabled) return // the paused overlay already says so
    val userSpeaking = uiState.cameraEnabled && (
        uiState.liveTranscript?.speaker == TranscriptSpeaker.USER ||
            uiState.turnState == TurnState.USER_SPEAKING ||
            uiState.turnState == TurnState.USER_TURN_FINALIZING
        )
    var justSent by remember { mutableStateOf(false) }
    var wasSpeaking by remember { mutableStateOf(false) }
    LaunchedEffect(userSpeaking) {
        if (wasSpeaking && !userSpeaking) {
            justSent = true
            delay(1_800L)
            justSent = false
        }
        wasSpeaking = userSpeaking
    }
    val (label, color) = when {
        !uiState.cameraEnabled -> "Camera paused" to TextMuted
        userSpeaking -> "Hold steady while you ask" to Amber
        justSent -> "✓  Frame sent to the agent" to Green
        else -> "Agent can see this · just ask" to TextPrimary
    }
    val pulse = rememberInfiniteTransition(label = "hint")
    val dotAlpha by pulse.animateFloat(1f, 0.3f, infiniteRepeatable(tween(600), RepeatMode.Reverse), label = "hint-dot")
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(Bg.copy(alpha = 0.72f))
            .border(BorderStroke(1.dp, color.copy(alpha = if (userSpeaking || justSent) 0.6f else 0f)), RoundedCornerShape(50))
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        if (userSpeaking) {
            Box(Modifier.size(6.dp).clip(CircleShape).background(Amber.copy(alpha = dotAlpha)))
            Spacer(Modifier.width(7.dp))
        }
        Text(label, style = Body.copy(fontSize = 12.sp, color = color, fontWeight = FontWeight.Medium))
    }
}

/** Four L-shaped corner brackets, like a camera viewfinder. */
@Composable
private fun ViewfinderCorners(color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val len = 22.dp.toPx()
        val w = 2.dp.toPx()
        val (right, bottom) = size.width to size.height
        fun corner(x: Float, y: Float, dx: Float, dy: Float) {
            drawLine(color, Offset(x, y), Offset(x + dx * len, y), w, StrokeCap.Round)
            drawLine(color, Offset(x, y), Offset(x, y + dy * len), w, StrokeCap.Round)
        }
        corner(0f, 0f, 1f, 1f)
        corner(right, 0f, -1f, 1f)
        corner(0f, bottom, 1f, -1f)
        corner(right, bottom, -1f, -1f)
    }
}

@Composable
private fun StartControls(uiState: ConversationUiState, onStart: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "mic-glow")
    val glow by transition.animateFloat(1f, 1.18f, infiniteRepeatable(tween(1400), RepeatMode.Reverse), label = "glow")
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
        Box(contentAlignment = Alignment.Center, modifier = Modifier.size(104.dp)) {
            if (!uiState.isStarting) {
                Box(Modifier.size(80.dp).scale(glow).clip(CircleShape).background(Amber.copy(alpha = 0.14f)))
            }
            Surface(
                onClick = onStart,
                enabled = !uiState.isStarting,
                shape = CircleShape,
                color = Amber,
                modifier = Modifier.size(76.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    if (uiState.isStarting) {
                        CircularProgressIndicator(color = Bg, strokeWidth = 3.dp, modifier = Modifier.size(28.dp))
                    } else {
                        Icon(Icons.Filled.Mic, contentDescription = "Start talking", tint = Bg, modifier = Modifier.size(32.dp))
                    }
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(
            if (uiState.isStarting) "Connecting to your co-driver…" else "Tap to talk · hands-free after that",
            style = Body.copy(fontSize = 13.sp),
        )
    }
}

@Composable
private fun ConversationControls(
    uiState: ConversationUiState,
    onEnd: () -> Unit,
    onToggleMicrophone: () -> Unit,
    onToggleCamera: () -> Unit,
) {
    // Call-style row: End · Mic (primary, larger) · Camera, centred with labels underneath.
    val micOn = uiState.micRequestedEnabled
    val glow = rememberInfiniteTransition(label = "mic-on")
    val ring by glow.animateFloat(1f, 1.22f, infiniteRepeatable(tween(1300), RepeatMode.Reverse), label = "mic-ring")
    Row(
        horizontalArrangement = Arrangement.spacedBy(36.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.Top,
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
    ) {
        // Power-off in red: clearly "switch the co-driver off", without looking like a phone hang-up.
        ControlButton(label = "End", size = 56.dp) {
            Surface(
                onClick = onEnd,
                enabled = !uiState.isStopping,
                shape = CircleShape,
                color = Red.copy(alpha = 0.14f),
                border = BorderStroke(1.5.dp, Red.copy(alpha = 0.8f)),
                modifier = Modifier.size(56.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Filled.PowerSettingsNew, contentDescription = "End the session", tint = Red)
                }
            }
        }
        ControlButton(label = if (micOn) "Mic on" else "Muted", size = 72.dp) {
            if (micOn) {
                Box(Modifier.size(72.dp).scale(ring).clip(CircleShape).background(Amber.copy(alpha = 0.16f)))
            }
            Surface(
                onClick = onToggleMicrophone,
                shape = CircleShape,
                color = if (micOn) Amber else CardTop,
                border = if (micOn) null else BorderStroke(1.5.dp, Red.copy(alpha = 0.7f)),
                modifier = Modifier.size(72.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        if (micOn) Icons.Filled.Mic else Icons.Filled.MicOff,
                        contentDescription = if (micOn) "Mute microphone" else "Unmute microphone",
                        tint = if (micOn) Bg else Red,
                        modifier = Modifier.size(30.dp),
                    )
                }
            }
        }
        ControlButton(label = if (uiState.cameraEnabled) "Camera" else "Camera off", size = 56.dp) {
            Surface(
                onClick = onToggleCamera,
                enabled = uiState.cameraPermissionGranted,
                shape = CircleShape,
                color = if (uiState.cameraEnabled) CardTop else Bg,
                border = BorderStroke(1.dp, if (uiState.cameraEnabled) Hairline else TextFaint),
                modifier = Modifier.size(56.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        if (uiState.cameraEnabled) Icons.Filled.Videocam else Icons.Filled.VideocamOff,
                        contentDescription = if (uiState.cameraEnabled) "Pause camera" else "Resume camera",
                        tint = if (uiState.cameraEnabled) TextPrimary else TextMuted,
                    )
                }
            }
        }
    }
}

/** A round control with its label centred underneath; buttons of different sizes share a baseline row. */
@Composable
private fun ControlButton(label: String, size: androidx.compose.ui.unit.Dp, button: @Composable () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(contentAlignment = Alignment.Center, modifier = Modifier.size(72.dp)) { button() }
        Spacer(Modifier.height(6.dp))
        Text(label, fontFamily = Inter, fontWeight = FontWeight.Medium, fontSize = 11.sp, color = TextMuted)
    }
}

private fun ConversationUiState.latestLine(speaker: TranscriptSpeaker): String? {
    liveTranscript?.takeIf { it.speaker == speaker && it.text.isNotBlank() }?.let { return it.text }
    return transcriptHistory.lastOrNull { it.speaker == speaker && it.text.isNotBlank() }?.text
}

/**
 * Shows the agent's reply in a scrollable box, revealed word by word while the
 * agent is actually speaking, newest word fading in. Agora delivers the transcript before the
 * audio starts, so revealing on arrival made the text run ahead of the voice.
 */
@Composable
private fun AgentCaption(full: String, speaking: Boolean, live: Boolean) {
    val words = remember(full) { full.normalizedWords() }
    var shown by remember { mutableIntStateOf(0) }
    var previousWords by remember { mutableStateOf(emptyList<String>()) }
    var spokeThisTurn by remember { mutableStateOf(false) }
    val isSpeaking by rememberUpdatedState(speaking)
    val newestAlpha = remember { Animatable(1f) }

    LaunchedEffect(full, live) {
        val shared = previousWords.zip(words).takeWhile { (a, b) -> a == b }.size
        if (shared == 0) spokeThisTurn = false
        shown = minOf(shown, shared)
        previousWords = words
        if (!live) {
            shown = words.size
            return@LaunchedEffect
        }
        while (shown < words.size) {
            when {
                isSpeaking -> {
                    spokeThisTurn = true
                    shown++
                    newestAlpha.snapTo(0f)
                    newestAlpha.animateTo(1f, tween(CAPTION_FADE_MS))
                    val behind = words.size - shown
                    delay(if (behind > CAPTION_CATCH_UP_WORDS) 40L else CAPTION_WORD_MS - CAPTION_FADE_MS)
                }
                // Voice finished (or was interrupted) before the reveal caught up: show the rest.
                spokeThisTurn -> shown = words.size
                else -> delay(50L) // text arrived before the voice: wait for speech to start
            }
        }
    }

    val visible = words.take(shown)
    val scroll = rememberScrollState()
    LaunchedEffect(shown) { scroll.animateScrollTo(scroll.maxValue) }
    if (visible.isEmpty()) return
    val text = buildAnnotatedString {
        visible.forEachIndexed { index, word ->
            if (index > 0) append(' ')
            val isNewest = index == visible.lastIndex && live && shown < words.size
            withStyle(SpanStyle(color = if (isNewest) TextPrimary.copy(alpha = newestAlpha.value) else TextPrimary)) {
                append(word)
            }
        }
    }
    Text(
        text = text,
        fontFamily = Grotesk,
        fontWeight = FontWeight.Medium,
        fontSize = 22.sp,
        lineHeight = 29.sp,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(max = 150.dp)
            .verticalScroll(scroll),
    )
}

/** Agora joins sentences without a space ("engine.You"); split those so pacing counts real words. */
private fun String.normalizedWords(): List<String> =
    replace(Regex("""([.!?,;:])(?=[A-Za-z])"""), "$1 ").split(Regex("""\s+""")).filter { it.isNotBlank() }

private const val CAPTION_WORD_MS = 340L // ElevenLabs Eric speaks ~175 words per minute
private const val CAPTION_FADE_MS = 120
private const val CAPTION_CATCH_UP_WORDS = 20
