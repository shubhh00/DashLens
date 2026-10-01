package com.dashlens.app.data

import com.dashlens.app.model.AgentInviteResult
import com.dashlens.app.model.AgoraTokenBundle
import com.dashlens.app.model.BackendHealthResult
import com.dashlens.app.model.RenewalTokens

class ConversationRepository(
    private val api: ConversationAgoraApi = ConversationAgoraApi(),
) {
    suspend fun checkHealth(): BackendHealthResult {
        return api.checkHealth()
    }

    suspend fun sendText(agentId: String, channelName: String, text: String, speak: Boolean, append: Boolean) {
        api.sendText(agentId, channelName, text, speak, append)
    }

    suspend fun requestSessionBootstrap(): AgoraTokenBundle {
        return api.requestSessionBootstrap()
    }

    suspend fun inviteAgent(
        channelName: String,
        requesterRtcUid: String,
    ): AgentInviteResult {
        return api.inviteAgent(
            channelName = channelName,
            requesterRtcUid = requesterRtcUid,
        )
    }

    suspend fun stopConversation(
        agentId: String,
        channelName: String,
    ) {
        api.stopConversation(agentId, channelName)
    }

    suspend fun interruptConversation(
        agentId: String,
        channelName: String,
    ) {
        api.interruptAgent(agentId, channelName)
    }

    suspend fun renewTokens(
        channel: String,
        rtcUid: Int,
        rtmUserId: String,
    ): RenewalTokens {
        return api.renewTokens(
            channel = channel,
            rtcUid = rtcUid,
            rtmUserId = rtmUserId,
        )
    }
}
