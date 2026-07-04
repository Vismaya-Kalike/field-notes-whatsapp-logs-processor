from __future__ import annotations

import logging
from dataclasses import dataclass

from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class ResolvedFacilitator:
    facilitator_id: str
    learning_centre_id: str
    name: str


class FacilitatorLookup:
    def __init__(self, client: Client) -> None:
        self._client = client
        self._facilitators: list[dict] = []
        self._lc_map: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        resp = self._client.table("facilitators").select("id, name, alias, contact_number").execute()
        self._facilitators = resp.data or []

        lc_resp = self._client.table("learning_centre_facilitators").select("facilitator_id, learning_centre_id").execute()
        for row in lc_resp.data or []:
            self._lc_map[row["facilitator_id"]] = row["learning_centre_id"]

        logger.info("Loaded %d facilitators, %d LC mappings", len(self._facilitators), len(self._lc_map))

    def resolve(self, sender: str) -> ResolvedFacilitator | None:
        fac = self._match(sender)
        if not fac:
            return None

        fac_id = fac["id"]
        lc_id = self._lc_map.get(fac_id)
        if not lc_id:
            logger.warning("No learning centre for facilitator %s (%s)", fac["name"], fac_id)
            return None

        return ResolvedFacilitator(
            facilitator_id=fac_id,
            learning_centre_id=lc_id,
            name=fac["name"],
        )

    def _match(self, sender: str) -> dict | None:
        for fac in self._facilitators:
            if fac["name"] == sender:
                return fac

        for fac in self._facilitators:
            aliases = fac.get("alias") or []
            if sender in aliases:
                return fac

        for fac in self._facilitators:
            if fac.get("contact_number") == sender:
                return fac

        return None
