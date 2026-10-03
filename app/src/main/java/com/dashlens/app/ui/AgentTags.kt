package com.dashlens.app.ui

/**
 * The agent starts its first reply after each manual lookup with a tag the server prepared, in
 * curly braces so the TTS skips it: `{car:Hyundai Creta|manual|Hyundai roadside assistance|18001024645}`.
 * The caption shows the reply without it; the app turns it into the source line and the stop
 * card's call button.
 */
internal enum class ManualSource { MANUAL, GENERAL, FETCHING }

internal data class CarTag(
    val name: String,
    val source: ManualSource,
    val helplineLabel: String? = null,
    val helplineNumber: String? = null,
)

/** The call card: [urgent] when the agent says to stop now, otherwise it only gave the helpline. */
internal data class CallCard(val urgent: Boolean, val helplineLabel: String?, val helplineNumber: String?)

internal object AgentTags {
    private val CAR_TAG = Regex("""\{\s*car\s*:([^{}]*)\}""", RegexOption.IGNORE_CASE)
    private val HELP_TAG = Regex("""\{\s*help\s*:([^{}]*)\}""", RegexOption.IGNORE_CASE)
    private val CLOSED_BRACES = Regex("""\{[^{}]*\}""")
    private val OPEN_BRACE_AT_END = Regex("""\{[^{}]*$""") // a tag still streaming in

    fun strip(text: String): String =
        text.replace(CLOSED_BRACES, " ").replace(OPEN_BRACE_AT_END, " ").replace(Regex("""\s{2,}"""), " ").trim()

    fun car(text: String): CarTag? {
        val fields = CAR_TAG.findAll(text).lastOrNull()?.groupValues?.get(1)?.split('|')?.map { it.trim() } ?: return null
        val name = fields.getOrNull(0)?.takeIf { it.isNotBlank() } ?: return null
        val source = when (fields.getOrNull(1)?.lowercase()) {
            "manual" -> ManualSource.MANUAL
            "fetching" -> ManualSource.FETCHING
            else -> ManualSource.GENERAL
        }
        val number = dialable(fields.getOrNull(3))
        return CarTag(name, source, fields.getOrNull(2)?.takeIf { it.isNotBlank() && number != null }, number)
    }

    private val STOP_ADVICE = Regex("""\b(pull over|stop now|stop the car|stop safely|stop driving)\b""", RegexOption.IGNORE_CASE)
    private val NEGATION = Regex("""\b(no need to|don't|do not|not|never|without)\s+(\w+\s+){0,2}$""", RegexOption.IGNORE_CASE)
    // "If any red lamp stays on after you start, pull over" is advice for later, not a verdict now.
    private val LATER = Regex("""\b(stays?|remains?|comes? back|after you start|once you start)\b""", RegexOption.IGNORE_CASE)
    private val SPOKEN_NUMBER = Regex("""\d(?:[\s,]*\d){9,11}""")

    /** Shows the stop card when the reply tells the driver to pull over now. */
    fun stopAdvice(text: String, car: CarTag?): CallCard? {
        val spoken = strip(text)
        STOP_ADVICE.findAll(spoken).firstOrNull { match ->
            val before = spoken.substring(0, match.range.first)
            val sentence = before.substring(before.lastIndexOfAny(charArrayOf('.', '!', '?', ';')) + 1)
            !NEGATION.containsMatchIn(before) && !(sentence.trim().startsWith("if ", ignoreCase = true) && LATER.containsMatchIn(sentence))
        } ?: return null
        // The verified helpline comes with the car tag; a number the agent spoke is the fallback.
        car?.helplineNumber?.let { return CallCard(true, car.helplineLabel, it) }
        val spokenNumber = dialable(SPOKEN_NUMBER.find(spoken)?.value)
        val brand = car?.name?.substringBefore(' ')
        return CallCard(true, brand?.let { "$it roadside assistance" }?.takeIf { spokenNumber != null }, spokenNumber)
    }

    private val HELPLINE_MENTION = Regex("""one eight hundred|1\s*8\s*0\s*0""", RegexOption.IGNORE_CASE)

    /** The stop card, or just the call button when the agent read out the helpline. */
    fun callCard(text: String, car: CarTag?): CallCard? {
        stopAdvice(text, car)?.let { return it }
        // {help:MG Motor India helpline|18001006464} from getRoadsideHelpline (brand only, no car tag).
        HELP_TAG.findAll(text).lastOrNull()?.groupValues?.get(1)?.split('|')?.map { it.trim() }?.let { fields ->
            dialable(fields.getOrNull(1))?.let { return CallCard(false, fields.getOrNull(0)?.takeIf { it.isNotBlank() }, it) }
        }
        val number = car?.helplineNumber ?: return null
        return if (HELPLINE_MENTION.containsMatchIn(strip(text))) CallCard(false, car.helplineLabel, number) else null
    }

    /** Indian helplines are 10-12 digits (1800 numbers); anything else is not a dialable number. */
    private fun dialable(value: String?): String? = value.orEmpty().filter(Char::isDigit).takeIf { it.length in 10..12 }
}

/** Groups a helpline for display: 18001024645 -> 1800 102 4645. */
internal fun formatHelpline(digits: String): String =
    if (digits.length == 11 && digits.startsWith("1800")) {
        "${digits.substring(0, 4)} ${digits.substring(4, 7)} ${digits.substring(7)}"
    } else {
        digits
    }
