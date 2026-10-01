package com.dashlens.app.config

import com.dashlens.app.BuildConfig

object ServerConfig {
    val backendBaseUrl: String = BuildConfig.DASHLENS_SERVER_URL.trim().trimEnd('/')

    fun missingRequiredValues(): List<String> {
        val missing = mutableListOf<String>()
        if (backendBaseUrl.isBlank()) {
            missing += "DASHLENS_SERVER_URL"
        }
        return missing
    }

    val isConfigured: Boolean
        get() = missingRequiredValues().isEmpty()

    fun startupHelpMessage(): String? {
        val missing = missingRequiredValues()
        if (missing.isEmpty()) {
            return null
        }
        return "Add ${missing.joinToString()} to local.properties after starting the Python server and HTTPS tunnel."
    }
}
