"""Observations for original ShipScanner; native ALAS owns filtering/loops."""
from ...oracle.errors import SemanticGateClosed
from ...oracle.old_retirement import read_old_retirement_cards


class AbandonedCvRetirementPorts:
    def retirement_set_abandoned_carrier_filter(self):
        self._check_old_reentry()
        self.refresh_gems_farming_dock_input_frame()
        adapter = self.open()
        adapter._package_gate()
        if adapter._dock_equipment_options().get('preserve_equipment', True):
            raise SemanticGateClosed('abandoned-CV retirement requires disassemble equipment policy')
        return adapter.oracle.set_enhancement_dock_filter(
            'cv', enhanceable_only=False, native_rarities=('N',),
            semantic_owner='retirement', native_extra='not_level_max')

    def retirement_scan_abandoned_carriers(self, scanner):
        self._check_old_reentry()
        if (self._old_retirement_batch is not None
                and self._old_retirement_batch['selections']
                and not self._old_retirement_batch['complete']):
            raise SemanticGateClosed('abandoned-CV scan cannot replace an unconfirmed selected batch')
        if getattr(scanner, '_semantic_retirement_session', None) is not None:
            raise SemanticGateClosed('native retirement scanner already has an observation owner')
        self.refresh_frame()
        oracle = self.open()._require_frame_observation_oracle()
        card_limit = len(scanner.grids.buttons)
        before, state, cards = read_old_retirement_cards(oracle, card_limit=card_limit)
        if before.selected_count:
            raise SemanticGateClosed('abandoned-CV scan cannot inherit unowned selection')
        observations = oracle.gems_farming_dock_candidates(
            ship_ids={c.template_id for c in cards},
            require_emotion=scanner.sub_scanners['emotion']._enabled) if cards else ()
        values = []
        for card in cards:
            matches = [item for item in observations
                       if item.button.raw.get('instance_id') == card.instance_id
                       and item.button.bounds == card.button.bounds]
            if len(matches) != 1:
                raise SemanticGateClosed('abandoned-CV native card observation is ambiguous')
            item, = matches
            if (item.ship_id, item.ship_name, item.level) != (card.template_id, card.name, card.level):
                raise SemanticGateClosed('abandoned-CV card identity changed within native observation')
            if item.ship_type != 'cv':
                raise SemanticGateClosed('native CV filter contradicts typed Dock card')
            fields = dict(rarity=item.rarity, level=item.level, emotion=item.emotion,
                          fleet=item.fleet_index, status=item.status, button=card)
            for name, prop in scanner.sub_scanners.items():
                if not prop._enabled:
                    fields[name] = None  # Native disabled-property semantics.
                elif fields[name] is None:
                    raise SemanticGateClosed('enabled native scanner observation is missing: ' + name)
            values.append(fields)
        self._register_old_retirement_cards(before, state, cards, ('N',), card_limit)
        # Logical ownership of this exact native scanner for one synchronous
        # observation call; it cannot redirect other scanners or task policies.
        scanner._semantic_retirement_session = self
        self._retirement_scanner_observation = (scanner, tuple(values))
        try:
            return scanner.scan(None)  # _scan consumes typed records, never pixels.
        finally:
            self._retirement_scanner_observation = None
            del scanner._semantic_retirement_session

    def retirement_ship_scanner_records(self, scanner):
        observation = getattr(self, '_retirement_scanner_observation', None)
        if observation is None or observation[0] is not scanner:
            raise SemanticGateClosed('native retirement scanner has no current observation scope')
        return observation[1]
