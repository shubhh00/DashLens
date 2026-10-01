package com.dashlens.app.rtc

import android.content.Context
import android.view.OrientationEventListener
import io.agora.base.JavaI420Buffer
import io.agora.base.VideoFrame
import io.agora.base.internal.video.YuvHelper
import io.agora.rtc2.RtcEngine
import io.agora.rtc2.video.IVideoFrameObserver

/**
 * Keeps the frames the agent sees upright however the phone is held, while the app UI stays
 * portrait. Runs at the pre-encoder position, so only the published stream is rotated and the
 * on-screen preview is untouched.
 *
 * With the UI locked to portrait, Agora rotates frames as if the phone were always upright, so a
 * phone held sideways (to fit a wide cluster) sent the agent a sideways image. We track the real
 * device angle and apply the standard back-camera correction:
 * upright rotation = (frame rotation + device angle) mod 360.
 */
class UprightFrameRotator(context: Context) {
    @Volatile
    private var deviceDegrees: Int = 0

    private val orientationListener = object : OrientationEventListener(context.applicationContext) {
        override fun onOrientationChanged(orientation: Int) {
            if (orientation == ORIENTATION_UNKNOWN) return
            deviceDegrees = when (orientation) {
                in 45 until 135 -> 90
                in 135 until 225 -> 180
                in 225 until 315 -> 270
                else -> 0
            }
        }
    }

    private val observer = object : IVideoFrameObserver {
        override fun onCaptureVideoFrame(sourceType: Int, videoFrame: VideoFrame?): Boolean = true

        override fun onPreEncodeVideoFrame(sourceType: Int, videoFrame: VideoFrame?): Boolean {
            val frame = videoFrame ?: return true
            val rotation = (frame.rotation + deviceDegrees) % 360
            if (rotation == 0 && frame.rotation == 0) return true
            val source = frame.buffer.toI420() ?: return true
            val sideways = rotation % 180 != 0
            val rotated = JavaI420Buffer.allocate(
                if (sideways) source.height else source.width,
                if (sideways) source.width else source.height,
            )
            YuvHelper.I420Rotate(
                source.dataY, source.strideY, source.dataU, source.strideU, source.dataV, source.strideV,
                rotated.dataY, rotated.strideY, rotated.dataU, rotated.strideU, rotated.dataV, rotated.strideV,
                source.width, source.height, rotation,
            )
            source.release()
            frame.replaceBuffer(rotated, 0, frame.timestampNs)
            return true
        }

        override fun onMediaPlayerVideoFrame(videoFrame: VideoFrame?, mediaPlayerId: Int): Boolean = true
        override fun onRenderVideoFrame(channelId: String?, uid: Int, videoFrame: VideoFrame?): Boolean = true
        override fun getVideoFrameProcessMode(): Int = IVideoFrameObserver.PROCESS_MODE_READ_WRITE
        override fun getVideoFormatPreference(): Int = IVideoFrameObserver.VIDEO_PIXEL_I420
        override fun getRotationApplied(): Boolean = false
        override fun getMirrorApplied(): Boolean = false
        override fun getObservedFramePosition(): Int = IVideoFrameObserver.POSITION_PRE_ENCODER
    }

    fun attach(engine: RtcEngine) {
        engine.registerVideoFrameObserver(observer)
        if (orientationListener.canDetectOrientation()) orientationListener.enable()
    }

    fun detach(engine: RtcEngine?) {
        orientationListener.disable()
        runCatching { engine?.registerVideoFrameObserver(null) }
    }
}
