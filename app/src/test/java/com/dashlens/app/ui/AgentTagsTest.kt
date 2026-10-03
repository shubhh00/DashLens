package com.dashlens.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class AgentTagsTest {
    private val creta = CarTag("Hyundai Creta", ManualSource.MANUAL, "Hyundai roadside assistance", "18001024645")

    @Test
    fun stripsClosedAndStreamingTags() {
        assertEquals("Pull over now.", AgentTags.strip("{car:Hyundai Creta|manual} Pull over now."))
        assertEquals("", AgentTags.strip("{car:Hyundai Cre"))
    }

    @Test
    fun readsCarSourceAndHelpline() {
        assertEquals(creta, AgentTags.car("{car:Hyundai Creta|manual|Hyundai roadside assistance|18001024645}Hi"))
        assertEquals(CarTag("Toyota Fortuner", ManualSource.FETCHING), AgentTags.car("{car: Toyota Fortuner | fetching}"))
        assertNull(AgentTags.car("No tags here."))
    }

    @Test
    fun stopCardUsesTheVerifiedHelpline() {
        val stop = AgentTags.stopAdvice("The oil lamp is on with the engine running: pull over now; the number is on your screen.", creta)
        assertEquals("18001024645", stop?.helplineNumber)
        assertEquals("1800 102 4645", formatHelpline(stop!!.helplineNumber!!))
        // Engine state given as a condition still means stop.
        assertNotNull(AgentTags.stopAdvice("If the engine is running, stop safely and switch it off.", creta))
    }

    @Test
    fun noStopCardForParkedOrLaterAdvice() {
        assertNull(AgentTags.stopAdvice("The car is parked, so there is no need to pull over.", creta))
        assertNull(AgentTags.stopAdvice("That is the seat belt lamp; fasten your belt.", creta))
        assertNull(AgentTags.stopAdvice("That is the self-check. If any red lamp stays lit after you start, pull over safely.", creta))
    }

    @Test
    fun spokenNumberIsTheFallback() {
        val car = CarTag("Kia Seltos", ManualSource.MANUAL)
        val stop = AgentTags.stopAdvice("Stop the car safely, then call Kia at 1 8 0 0, 1 0 8, 5 0 0 0.", car)
        assertEquals("18001085000", stop?.helplineNumber)
        assertEquals("Kia roadside assistance", stop?.helplineLabel)
    }

    @Test
    fun callButtonWhenTheHelplineIsGiven() {
        val card = AgentTags.callCard("The Kia helpline is one eight hundred, one zero eight, five zero zero zero.", creta)
        assertEquals(false, card?.urgent)
        assertEquals("18001024645", card?.helplineNumber)
        assertEquals(true, AgentTags.callCard("Pull over now.", creta)?.urgent)
        assertNull(AgentTags.callCard("That is the seat belt lamp.", creta))
    }
}
