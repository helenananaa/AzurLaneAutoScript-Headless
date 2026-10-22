"""Pinned native method fixtures extracted from the current applied ALAS series.
Only selected observation/watcher bodies; compare ASTs with current sources when available.
"""

class CampaignStatus:

    def _get_oil(self):
        from alas_headless import current_semantic_session
        semantic_session = current_semantic_session()
        if semantic_session is not None:
            return semantic_session.campaign_oil()
        _ = self.appear(OCR_OIL_CHECK)
        color = get_color(self.device.image, OCR_OIL_CHECK.button)
        if color_similar(color, OCR_OIL_CHECK.color):
            if server.server != 'jp':
                ocr = Digit(OCR_OIL, name='OCR_OIL', letter=(247, 247, 247), threshold=128)
            else:
                ocr = Digit(OCR_OIL, name='OCR_OIL', letter=(201, 201, 201), threshold=128)
        elif color_similar(color, (59, 59, 64)):
            ocr = Digit(OCR_OIL, name='OCR_OIL', letter=(165, 165, 165), threshold=128)
        else:
            logger.warning(f'Unexpected OCR_OIL_CHECK color')
            ocr = Digit(OCR_OIL, name='OCR_OIL', letter=(247, 247, 247), threshold=128)
        return ocr.ocr(self.device.image)

    def get_coin(self, skip_first_screenshot=True):
        """
            Returns:
                int: Coin amount
            """
        from alas_headless import current_semantic_session
        semantic_session = current_semantic_session()
        if semantic_session is not None:
            return semantic_session.event_coin()
        amount = 0
        timeout = Timer(1, count=2).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()
            if timeout.reached():
                logger.warning('Get coin timeout')
                break
            amount = OCR_COIN.ocr(self.device.image)
            if amount >= 100:
                break
        return amount

class AutoSearchCombat:

    def auto_search_watch_oil(self, checked=False):
        """
            Watch oil.
            This will set auto_search_oil_limit_triggered.
            """
        if not checked:
            oil = self._get_oil()
            if oil == 0:
                logger.warning('Oil not found')
            else:
                if oil < max(500, self.config.StopCondition_OilLimit):
                    logger.info('Reach oil limit')
                    self.auto_search_oil_limit_triggered = True
                else:
                    if self.auto_search_oil_limit_triggered:
                        logger.warning('auto_search_oil_limit_triggered but oil recovered, probably because of wrong OCR result before')
                    self.auto_search_oil_limit_triggered = False
                checked = True
        return checked

    def auto_search_watch_coin(self, checked=False):
        """
            Watch coin.
            This will set auto_search_coin_limit_triggered.
            """
        if not checked:
            limit = self.config.TaskBalancer_CoinLimit
            coin = self.get_coin()
            if coin == 0:
                logger.warning('Coin not found')
            else:
                if self.is_balancer_task():
                    if coin < limit:
                        logger.info('Reach coin limit')
                        self.auto_search_coin_limit_triggered = True
                    else:
                        self.auto_search_coin_limit_triggered = False
                else:
                    if self.auto_search_coin_limit_triggered:
                        logger.warning('auto_search_coin_limit_triggered but coin recovered, probably because of wrong OCR result before')
                    self.auto_search_coin_limit_triggered = False
                checked = True
        return checked

    def _handle_auto_search_menu_missing(self):
        """
            Sometimes game is bugged, auto search menu is not shown.
            After BOSS battle, it enters campaign directly.
            To handle this, if game in campaign for a certain time, it means auto search ends.

            Returns:
                bool: If triggered
            """
        if self.is_in_stage():
            if self._auto_search_in_stage_timer.reached():
                logger.info('Catch auto search menu missing')
                return True
        else:
            self._auto_search_in_stage_timer.reset()
        return False

    def auto_search_combat_status(self):
        """
            Pages:
                in: any
                out: is_auto_search_running()
            """
        logger.info('Auto Search combat status')
        self.device.stuck_record_clear()
        self.device.click_record_clear()
        exp_info = False
        for _ in self.loop():
            if self.is_auto_search_running():
                self._auto_search_status_confirm = False
                break
            if self.is_in_auto_search_menu() or self._handle_auto_search_menu_missing():
                raise CampaignEnd
            if self.handle_get_ship():
                continue
            if self.handle_auto_search_map_option():
                self._auto_search_status_confirm = False
                continue
            if self.handle_popup_confirm('AUTO_SEARCH_COMBAT_STATUS'):
                continue
            if self.handle_urgent_commission():
                continue
            if self.handle_story_skip():
                continue
            if self.handle_guild_popup_cancel():
                continue
            if self.handle_vote_popup():
                continue
            if self.handle_mission_popup_ack():
                continue
            if self._auto_search_status_confirm:
                if not exp_info and self.handle_get_ship():
                    continue
                if self.handle_get_items():
                    continue
                if self.handle_battle_status():
                    continue
                if self.handle_popup_confirm('combat_status'):
                    continue
                if self.handle_exp_info():
                    exp_info = True
                    continue

    def auto_search_combat_execute(self, emotion_reduce, fleet_index):
        """
        Args:
            emotion_reduce (bool):
            fleet_index (int):

        Pages:
            in: is_combat_loading()
            out: combat status
        """
        logger.info('Auto search combat loading')
        self.device.stuck_record_clear()
        self.device.click_record_clear()
        self.device.screenshot_interval_set('combat')
        for _ in self.loop():
            if self.handle_combat_automation_confirm():
                continue
            if getattr(self.device, 'semantic_adapter', None) is not None:
                if self.handle_popup_confirm('AUTO_SEARCH_COMBAT_LOADING'):
                    continue
                if self.handle_urgent_commission():
                    continue
                if self.handle_guild_popup_cancel():
                    continue
            if self.handle_story_skip():
                continue
            if self.handle_vote_popup():
                continue
            if self.is_in_auto_search_menu() or self._handle_auto_search_menu_missing():
                raise CampaignEnd
            pause = self.is_combat_executing()
            if pause:
                logger.attr('BattleUI', pause)
                break
        logger.info('Auto Search combat execute')
        self.submarine_call_reset()
        submarine_mode = 'do_not_use'
        if self.config.Submarine_Fleet:
            submarine_mode = self.config.Submarine_Mode
        self.combat_auto_reset()
        self.combat_manual_reset()
        self.device.stuck_record_clear()
        self.device.click_record_clear()
        if emotion_reduce:
            self.emotion.reduce(fleet_index)
        auto = self.config.Fleet_Fleet1Mode if fleet_index == 1 else self.config.Fleet_Fleet2Mode
        for _ in self.loop():
            if self.handle_submarine_call(submarine_mode):
                continue
            if self.handle_combat_auto(auto):
                continue
            if self.handle_combat_manual(auto):
                continue
            if auto != 'combat_auto' and self.auto_mode_checked and self.is_combat_executing():
                if self.handle_combat_weapon_release():
                    continue
            if self.handle_popup_confirm('AUTO_SEARCH_COMBAT_EXECUTE'):
                continue
            if self.handle_urgent_commission():
                continue
            if self.handle_story_skip():
                continue
            if self.handle_guild_popup_cancel():
                continue
            if self.handle_vote_popup():
                continue
            if self.handle_mission_popup_ack():
                continue
            if self.is_in_auto_search_menu() or self._handle_auto_search_menu_missing():
                self.device.screenshot_interval_set()
                raise CampaignEnd
            if self.is_combat_executing():
                continue
            if self.handle_get_ship():
                continue
            if self.appear(BATTLE_STATUS_S) or self.appear(BATTLE_STATUS_A) or self.appear(BATTLE_STATUS_B) or self.appear(EXP_INFO_S) or self.appear(EXP_INFO_A) or self.appear(EXP_INFO_B) or self.is_auto_search_running():
                self.device.screenshot_interval_set()
                break
            if self.auto_search_combat_end():
                break

class EnemySearchingHandler:

    def is_in_stage_page(self):
        for check in [CAMPAIGN_CHECK, EVENT_CHECK, SP_CHECK]:
            if self.appear(check, offset=(20, 20)):
                return True
        return False

    def is_in_stage(self):
        if not self.is_in_stage_page():
            return False
        if not self.is_stage_page_has_entrance():
            return False
        return True

class AutoSearchHandler:

    def is_auto_search_running(self):
        """
            Returns:
                bool:
            """
        semantic_adapter = getattr(self.device, 'semantic_adapter', None)
        if semantic_adapter is not None:
            return semantic_adapter.campaign_auto_search_map_running()
        return self.appear(AUTO_SEARCH_MAP_OPTION_ON, offset=self._auto_search_offset) and self.appear(AUTO_SEARCH_MAP_OPTION_ON)

    def is_in_auto_search_menu(self):
        """
            Returns:
                bool:
            """
        semantic_adapter = getattr(self.device, 'semantic_adapter', None)
        if semantic_adapter is not None:
            return semantic_adapter.campaign_auto_search_result_visible()
        return AUTO_SEARCH_MENU_CONTINUE.match_luma(self.device.image, offset=self._auto_search_menu_offset)

    def handle_auto_search_map_option(self):
        """
            Ensure auto search option in map is ON

            Returns:
                bool: If clicked
            """
        if self.appear(AUTO_SEARCH_MAP_OPTION_OFF, offset=self._auto_search_offset) and self.appear_then_click(AUTO_SEARCH_MAP_OPTION_OFF, interval=2):
            return True
        return False

class Level:

    def lv_get(self, after_battle=False):
        """
        Args:
            after_battle (bool): True if called after battle else False.

        Returns:
            list[int]:
        """
        if not self.config.StopCondition_ReachLevel and (not self.config.STOP_IF_REACH_LV32):
            return [-1] * 6
        self._lv_before_battle = self.lv if after_battle else [-1] * 6
        from alas_headless import current_semantic_session
        semantic_session = current_semantic_session()
        if semantic_session is not None:
            self.lv = list(semantic_session.campaign_fleet_levels())
        else:
            ocr = LevelOcr(self._lv_grid().buttons, name='LevelOcr')
            self.lv = ocr.ocr(self.device.image)
        logger.attr('LEVEL', ', '.join((str(data) for data in self.lv)))
        if after_battle:
            self.lv_triggered()
            self.lv32_triggered()
        return self.lv

    def lv_triggered(self):
        limit = self.config.StopCondition_ReachLevel
        if not limit:
            return False
        for i in range(6):
            before, after = (self._lv_before_battle[i], self.lv[i])
            if after > before > 0:
                logger.info(f'Position {i} LV.{before} -> LV.{after}')
            if after >= limit > before > 0:
                if after - before == 1 or after < 35:
                    logger.info(f'Position {i} LV.{limit} Reached')
                    self.config.LV_TRIGGERED = True
                    return True
                else:
                    logger.warning(f'Level gap between {before} and {after} is too large. This will not be considered as a trigger')
        return False

    def lv32_triggered(self):
        if not self.config.STOP_IF_REACH_LV32:
            return False
        if self.lv[0] >= 32:
            logger.info(f'Position 0 LV.32 Reached')
            self.config.LV32_TRIGGERED = True
            return True
        return False
