import logging
from datetime import datetime
from typing import Any, Dict, Union

from .exceptions import NotFoundException
from .utils import BaseDict

_LOGGER = logging.getLogger(__name__)


STATUS = {
    0: "OFFLINE",
    1: "DISCONNECTED",
    2: "AWAITING_START",
    3: "CHARGING",
    4: "COMPLETED",
    5: "ERROR",
    6: "READY_TO_CHARGE",
}

NODE_TYPE = {1: "Master", 2: "Extender"}

PHASE_MODE = {1: "Locked to single phase", 2: "Auto", 3: "Locked to three phase"}

REASON_FOR_NO_CURRENT = {
    # Work-in-progress, must be taken with a pinch of salt, as per now just reverse engineering of observations until API properly documented
    None: "No reason",
    0: "No reason, charging or ready to charge",
    1: "Charger paused",
    2: "Charger paused",
    3: "Charger paused",
    4: "Charger paused",
    5: "Charger paused",
    6: "Charger paused",
    9: "Error no current",
    50: "Secondary unit not requesting current or no car connected",
    51: "Charger paused",
    52: "Charger paused",
    53: "Charger disabled",
    54: "Waiting for schedule/auth",
    55: "Pending auth",
}


class ChargerState(BaseDict):
    """ Charger state with integer enum values converted to human readable string values"""

    def __init__(self, state: Dict[str, Any], raw=False):
        if not raw:
            data = {
                **state,
                "chargerOpMode": STATUS[state["chargerOpMode"]],
                "reasonForNoCurrent": f"({state['reasonForNoCurrent']}) {REASON_FOR_NO_CURRENT.get(state['reasonForNoCurrent'], 'Unknown')}",
            }
        else:
            data = {
                **state,
                "reasonForNoCurrent": "none" if state["reasonForNoCurrent"] is None else state["reasonForNoCurrent"],
            }
        super().__init__(data)


class ChargerConfig(BaseDict):
    """ Charger config with integer enum values converted to human readable string values"""

    def __init__(self, config: Dict[str, Any], raw=False):
        if not raw:
            data = {
                **config,
                "localNodeType": NODE_TYPE[config["localNodeType"]],
                "phaseMode": PHASE_MODE[config["phaseMode"]],
            }
        else:
            data = {**config}
        super().__init__(data)


class ChargerSchedule(BaseDict):
    """ Charger charging schedule/plan """

    def __init__(self, schedule: Dict[str, Any]):
        data = {
            "id": schedule.get("id"),
            "chargeStartTime": schedule.get("chargeStartTime"),
            "chargeStopTime": schedule.get("chargeStopTime"),
            "repeat": schedule.get("repeat"),
        }
        super().__init__(data)


class ChargerSession(BaseDict):
    """ Charger charging session """

    def __init__(self, session: Dict[str, Any]):
        data = {
            "carConnected": session.get("carConnected"),
            "carDisconnected": session.get("carDisconnected"),
            "kiloWattHours": float(session.get("kiloWattHours")),
        }
        super().__init__(data)


class Charger(BaseDict):
    def __init__(self, entries: Dict[str, Any], easee: Any, site: Any = None, circuit: Any = None):
        super().__init__(entries)
        self.id: str = entries["id"]
        self.name: str = entries["name"]
        self.site = site
        self.circuit = circuit
        self.easee = easee

    async def get_consumption_between_dates(self, from_date: datetime, to_date):
        """ Gets consumption between two dates """
        value = await (
            await self.easee.get(f"/api/sessions/charger/{self.id}/total/{from_date.isoformat()}/{to_date.isoformat()}")
        ).text()
        return float(value)

    async def get_sessions_between_dates(self, from_date: datetime, to_date):
        """ Gets charging sessions between two dates """
        sessions = await (
            await self.easee.get(
                f"/api/sessions/charger/{self.id}/sessions/{from_date.isoformat()}/{to_date.isoformat()}"
            )
        ).json()
        sessions = [ChargerSession(session) for session in sessions]
        sessions.sort(key=lambda x: x["carConnected"], reverse=True)

        return sessions

    async def get_config(self, from_cache=False, raw=False) -> ChargerConfig:
        """ get config for charger """
        config = await (await self.easee.get(f"/api/chargers/{self.id}/config")).json()
        return ChargerConfig(config, raw)

    async def get_state(self, raw=False) -> ChargerState:
        """ get state for charger """
        state = await (await self.easee.get(f"/api/chargers/{self.id}/state")).json()
        return ChargerState(state, raw)

    async def start(self):
        """Start charging session"""
        return await self.easee.post(f"/api/chargers/{self.id}/commands/start_charging")

    async def pause(self):
        """Pause charging session"""
        return await self.easee.post(f"/api/chargers/{self.id}/commands/pause_charging")

    async def resume(self):
        """Resume charging session"""
        return await self.easee.post(f"/api/chargers/{self.id}/commands/resume_charging")

    async def stop(self):
        """Stop charging session"""
        return await self.easee.post(f"/api/chargers/{self.id}/commands/stop_charging")

    async def toggle(self):
        """Toggle charging session start/stop/pause/resume """
        return await self.easee.post(f"/api/chargers/{self.id}/commands/toggle_charging")

    async def get_basic_charge_plan(self) -> ChargerSchedule:
        """Get and return charger basic charge plan setting from cloud """
        try:
            plan = await self.easee.get(f"/api/chargers/{self.id}/basic_charge_plan")
            plan = await plan.json()
            _LOGGER.debug(plan)
            return ChargerSchedule(plan)
        except (NotFoundException):
            _LOGGER.debug("No scheduled charge plan")
            return None

    # TODO: document types
    async def set_basic_charge_plan(self, id, chargeStartTime, chargeStopTime, repeat=True):
        """Set and post charger basic charge plan setting to cloud """
        json = {
            "id": id,
            "chargeStartTime": str(chargeStartTime),
            "chargeStopTime": str(chargeStopTime),
            "repeat": repeat,
        }
        return await self.easee.post(f"/api/chargers/{self.id}/basic_charge_plan", json=json)

    async def enable_charger(self, enable: bool):
        """Enable and disable charger in charger settings """
        json = {"enabled": enable}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def enable_idle_current(self, enable: bool):
        """Enable and disable idle current in charger settings """
        json = {"enableIdleCurrent": enable}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def limitToSinglePhaseCharging(self, enable: bool):
        """Limit to single phase charging in charger settings """
        json = {"limitToSinglePhaseCharging": enable}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def phaseMode(self, mode: int = 2):
        """Set charging phase mode, 1 = always 1-phase, 2 = auto, 3 = always 3-phase """
        json = {"phaseMode": mode}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def lockCablePermanently(self, enable: bool):
        """Lock and unlock cable permanently in charger settings """
        json = {"lockCablePermanently": enable}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def smartButtonEnabled(self, enable: bool):
        """Enable and disable smart button in charger settings """
        json = {"smartButtonEnabled": enable}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def delete_basic_charge_plan(self):
        """Delete charger basic charge plan setting from cloud """
        return await self.easee.delete(f"/api/chargers/{self.id}/basic_charge_plan")

    async def override_schedule(self):
        """Override scheduled charging and start charging"""
        return await self.easee.post(f"/api/chargers/{self.id}/commands/override_schedule")

    async def smart_charging(self, enable: bool):
        """Set charger smart charging setting"""
        json = {"smartCharging": enable}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def reboot(self):
        """Reboot charger"""
        return await self.easee.post(f"/api/chargers/{self.id}/commands/reboot")

    async def update_firmware(self):
        """Update charger firmware"""
        return await self.easee.post(f"/api/chargers/{self.id}/commands/update_firmware")

    async def set_dynamic_charger_circuit_current(self, currentP1: int, currentP2: int = None, currentP3: int = None):
        """ Set circuit dynamic current for charger """
        if self.circuit is not None:
            return await self.circuit.set_dynamic_current(currentP1, currentP2, currentP3)
        else:
            _LOGGER.info("Circuit info must be initialized for dynamic current to be set")

    async def set_max_charger_circuit_current(self, currentP1: int, currentP2: int = None, currentP3: int = None):
        """ Set circuit max current for charger """
        if self.circuit is not None:
            return await self.circuit.set_max_current(currentP1, currentP2, currentP3)
        else:
            _LOGGER.info("Circuit info must be initialized for max current to be set")

    async def set_max_offline_charger_circuit_current(
        self, currentP1: int, currentP2: int = None, currentP3: int = None
    ):
        """ Set circuit max offline current for charger, fallback value for limit if charger is offline """
        if self.circuit is not None:
            return await self.circuit.set_max_offline_current(currentP1, currentP2, currentP3)
        else:
            _LOGGER.info("Circuit info must be initialized for offline current to be set")

    async def set_dynamic_charger_current(self, current: int):
        """ Set charger dynamic current """
        json = {"dynamicChargerCurrent": current}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def set_max_charger_current(self, current: int):
        """ Set charger max current """
        json = {"maxChargerCurrent": current}
        return await self.easee.post(f"/api/chargers/{self.id}/settings", json=json)

    async def set_access(self, access: Union[int, str]):
        """ Set the level of access for a changer """
        json = {
            1: 1,
            2: 2,
            3: 3,
            "open_for_all": 1,
            "easee_account_required": 2,
            "whitelist": 3,
        }

        return await self.easee.put(f"/api/chargers/{self.id}/access", json=json[access])

    async def delete_access(self):
        """ Revert permissions overridden on a charger level"""
        return await self.easee.delete(f"/api/chargers/{self.id}/access")
