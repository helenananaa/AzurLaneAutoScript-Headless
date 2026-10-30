"""Frozen native244 methods; original task loops, typed boundary adaptation."""

class Retirement:
    def _retirement_confirm(self, skip_first_screenshot=True):
        """
        Pages:
            in: IN_RETIREMENT_CHECK, and also
                SHIP_CONFIRM_2 if using one_click_retire
                SHIP_CONFIRM if using old_retire
            out: IN_RETIREMENT_CHECK
        """
        semantic_session = getattr(self.device, 'semantic_adapter', None)
        semantic_old_retire = (semantic_session is not None and
            getattr(semantic_session, 'old_retirement_confirmation_pending', lambda: False)())
        if semantic_old_retire:
            semantic_session.begin_old_retirement_confirmation()
        logger.info('Retirement confirm')
        executed = False
        for button in [SHIP_CONFIRM, SHIP_CONFIRM_2, EQUIP_CONFIRM, EQUIP_CONFIRM_2, GET_ITEMS_1, SR_SSR_CONFIRM]:
            self.interval_clear(button)
        self.popup_interval_clear()
        timeout = Timer(10, count=10).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            # End
            if timeout.reached():
                # Ships being used by GemsFarming have no equipment to disassemble
                # So `executed` is never set to True, causing infinite loop
                # Handled with dirty timeout, a better fix is required
                logger.warning('Wait _retirement_confirm timeout, assume finished')
                break
            # sometimes you have EQUIP_CONFIRM without black-blurred background
            # EQUIP_CONFIRM and IN_RETIREMENT_CHECK appears
            if self.appear(IN_RETIREMENT_CHECK, offset=(20, 20)) and not self.appear(EQUIP_CONFIRM, offset=(30, 30)):
                if executed:
                    break
            else:
                timeout.reset()

            # Click
            # Ship confirm, order by display hierarchy
            if self._unable_to_enhance \
                    or self.config.OldRetire_SR \
                    or self.config.OldRetire_SSR \
                    or self.config.Retirement_RetireMode == 'one_click_retire':
                if self.handle_popup_confirm(name='RETIRE_SR_SSR', offset=(20, 50)):
                    # Avoid clicking the undelying SHIP_CONFIRM again
                    self.interval_reset([SHIP_CONFIRM, SHIP_CONFIRM_2])
                    # EQUIP_CONFIRM_2 may be detected as popup confirm
                    self.interval_reset([EQUIP_CONFIRM, EQUIP_CONFIRM_2])
                    continue
                if self.config.SERVER in ['cn', 'jp', 'tw'] and \
                        self.appear_then_click(SR_SSR_CONFIRM, offset=(20, 50), interval=2):
                    # Avoid clicking the undelying SHIP_CONFIRM again
                    self.interval_reset([SHIP_CONFIRM, SHIP_CONFIRM_2])
                    # EQUIP_CONFIRM_2 may be detected as popup confirm
                    self.interval_reset([EQUIP_CONFIRM, EQUIP_CONFIRM_2])
                    continue
            if self.match_template_color(SHIP_CONFIRM_2, offset=(30, 30), interval=2):
                if self.retire_keep_common_cv and not self._have_kept_cv:
                    self.keep_one_common_cv()
                self.device.click(SHIP_CONFIRM_2)
                # GET_ITEMS_1 is going to appear, avoid re-entering ship confirm
                self.interval_clear(GET_ITEMS_1)
                self.interval_reset([SHIP_CONFIRM, SHIP_CONFIRM_2])
                continue
            if self.match_template_color(SHIP_CONFIRM, offset=(30, 30), interval=2):
                self.device.click(SHIP_CONFIRM)
                continue
            # Equip confirm
            if self.appear_then_click(EQUIP_CONFIRM, offset=(30, 30), interval=2):
                continue
            if self.appear_then_click(EQUIP_CONFIRM_2, offset=(30, 30), interval=2):
                self.interval_clear(GET_ITEMS_1)
                executed = True
                continue
            # Get items
            if self.appear(GET_ITEMS_1, offset=(30, 30), interval=2):
                self.device.click(GET_ITEMS_1_RETIREMENT_SAVE)
                self.interval_reset(SHIP_CONFIRM)
                # equipment confirms are the next to appear
                self.interval_clear([EQUIP_CONFIRM, EQUIP_CONFIRM_2])
                continue
        if semantic_old_retire:
            semantic_session.finish_old_retirement_confirmation()


    def retire_ships_one_click(self):
        from alas_headless import current_semantic_session, SemanticGateClosed
        semantic_session = current_semantic_session()
        if semantic_session is not None:
            if self.retire_keep_common_cv:
                cv_policy = getattr(semantic_session, 'retire_ships_with_common_cv_policy', None)
                if not callable(cv_policy):
                    raise SemanticGateClosed('retirement common-CV preservation port is unavailable')
                self._have_kept_cv = False
                return cv_policy(
                    keep_limit_break=(self.config.OneClickRetire_KeepLimitBreak == 'keep_limit_break'),
                    native_keep=self.keep_one_common_cv)
            # ALAS still owns retirement timing and retry policy.  The semantic
            # port owns the official one-click transaction so its real selected
            # count, protection settings, confirmations, and equipment outcome
            # are proven without framebuffer access or a hard-coded batch size.
            return semantic_session.retire_ships_one_click(
                keep_limit_break=(
                    self.config.OneClickRetire_KeepLimitBreak
                    == 'keep_limit_break'
                )
            )
        logger.hr('Retirement')
        logger.info('Using one click retirement.')
        # No need to wait, one-click-retire doesn't need to check dock
        self.dock_favourite_set(wait_loading=False)
        self.dock_sort_method_dsc_set(wait_loading=False)
        end = False
        total = 0

        if self.retire_keep_common_cv:
            self._have_kept_cv = False

        while 1:
            self.handle_info_bar()

            # ONE_CLICK_RETIREMENT -> SHIP_CONFIRM_2 or info_bar_count
            skip_first_screenshot = True
            click_count = 0
            while 1:
                if skip_first_screenshot:
                    skip_first_screenshot = False
                else:
                    self.device.screenshot()
                # End
                if self.appear(SHIP_CONFIRM_2, offset=(30, 30)):
                    break
                if self.info_bar_count():
                    logger.info('No more ships to retire.')
                    end = True
                    break

                # Click
                if click_count >= 5:
                    logger.warning('Failed to select ships using ONE_CLICK_RETIREMENT after 5 trial')
                    if self._retire_wait_slow_retire():
                        # Waited, all good
                        # Use pass to trigger ONE_CLICK_RETIREMENT on the same screenshot
                        pass
                    else:
                        # probably because game bugged, a re-enter should fix it
                        # Mark as retire finished, higher level will call retires
                        end = True
                        total = 10
                        break
                if self.appear_then_click(ONE_CLICK_RETIREMENT, offset=(20, 20), interval=2):
                    click_count += 1
                    continue

            # info_bar_count
            if end:
                break
            # SHIP_CONFIRM_2 -> IN_RETIREMENT_CHECK
            self._retirement_confirm()
            total += 10
            # if total >= amount:
            #     break
            # Always break, since game client retire all once
            break

        logger.info(f'Total retired round: {total // 10}')
        return total


    def retire_ships_old(self, amount=None, rarity=None):
        """
        Args:
            amount (int): Amount of cards retire. 0 to 2000.
            rarity (tuple(str)): Card rarity. N, R, SR, SSR.

        Returns:
            int: Total retired.
        """
        if amount is None:
            amount = self._retire_amount
        if rarity is None:
            rarity = self._retire_rarity
        logger.hr('Retirement')
        logger.info(f'Amount={amount}. Rarity={rarity}')

        # transfer N R SR SSR to filter name
        correspond_name = {
            'N': 'common',
            'R': 'rare',
            'SR': 'elite',
            'SSR': 'super_rare'
        }
        _rarity = [correspond_name[i] for i in rarity]
        semantic_session = getattr(self.device, 'semantic_adapter', None)
        if semantic_session is not None:
            if self.retire_keep_common_cv:
                from alas_headless import SemanticGateClosed
                cv_policy = getattr(semantic_session, 'require_old_retirement_with_cv_policy', None)
                if not callable(cv_policy):
                    raise SemanticGateClosed('old retirement common-CV preservation port is unavailable')
                cv_policy()
            else:
                semantic_session.require_old_retirement_policy(keep_common_cv=False)
            semantic_session.old_retirement_set_sort(False)
            semantic_session.old_retirement_set_favourite(False)
            semantic_session.old_retirement_set_filter(
                sort='level', index='all', faction='all', rarity=_rarity, extra='no_limit')
        else:
            self.dock_sort_method_dsc_set(False, wait_loading=False)
            self.dock_favourite_set(False, wait_loading=False)
            self.dock_filter_set(
                sort='level', index='all', faction='all', rarity=_rarity, extra='no_limit')

        total = 0

        if self.retire_keep_common_cv:
            self._have_kept_cv = False

        while amount:
            selected = self._retirement_choose(
                amount=10 if amount > 10 else amount, target_rarity=rarity)
            total += selected
            if selected == 0:
                break
            self.device.screenshot()
            if not self.match_template_color(SHIP_CONFIRM, offset=(30, 30)):
                logger.warning('No ship selected, retrying')
                continue

            self._retirement_confirm()

            amount -= selected
            if amount <= 0:
                break

            self.handle_dock_cards_loading()
            continue

        if semantic_session is not None:
            semantic_session.old_retirement_set_sort(True)
            semantic_session.old_retirement_set_filter()
        else:
            self.dock_sort_method_dsc_set(True, wait_loading=False)
            self.dock_filter_set()
        logger.info(f'Total retired: {total}')
        return total


    def retire_gems_farming_flagships(self, keep_one=True) -> int:
        """
        Retire abandoned flagships of GemsFarming.
        Common CV whose level > 1, fleet is none and status is free
        will be regarded as targets.
        """
        logger.info('Retire abandoned flagships of GemsFarming')

        gems_farming_enable: bool = self.config.is_task_enabled('GemsFarming')
        if not gems_farming_enable:
            logger.info('Not in GemsFarming, skip')
            return 0

        semantic_session = getattr(self.device, 'semantic_adapter', None)
        if semantic_session is not None:
            semantic_session.old_retirement_set_favourite(False)
            semantic_session.old_retirement_set_sort(False)
            semantic_session.retirement_set_abandoned_carrier_filter()
        else:
            self.dock_favourite_set(wait_loading=False)
            self.dock_sort_method_dsc_set(wait_loading=False)
            self.dock_filter_set(index='cv', rarity='common', extra='not_level_max', sort='level')

        scanner = ShipScanner(
            rarity='common', fleet=0, status='free', level=(2, 100))
        scanner.disable('emotion')

        total = 0
        _ = self._have_kept_cv
        self._have_kept_cv = True

        skip_first_screenshot = True
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            self.handle_info_bar()
            if semantic_session is not None:
                ships = semantic_session.retirement_scan_abandoned_carriers(scanner)
            else:
                ships = scanner.scan(self.device.image)
            if not ships:
                # exit if nothing can be retired
                break
            if keep_one:
                if len(ships) < 2:
                    break
                else:
                    # Try to keep the one with the lowest level
                    ships.sort(key=lambda s: -s.level)
                    ships = ships[:-1]

            for ship in ships:
                if semantic_session is not None:
                    semantic_session.old_retirement_select_card(ship.button)
                else:
                    self.device.click(ship.button)
                self.device.sleep((0.1, 0.15))
                total += 1

            self._retirement_confirm()

            # Quick exit if there's only a few CV to retire
            if len(ships) < 10:
                break

        self._have_kept_cv = _
        # No need to wait, retire finished, just about to exit
        if semantic_session is not None:
            semantic_session.old_retirement_set_filter()
        else:
            self.dock_filter_set(wait_loading=False)

        return total


    def _retire_select_one(self, button, skip_first_screenshot=True):
        """
        Args:
            button (Button): Ship button to select
            skip_first_screenshot:
        """
        semantic_session = getattr(self.device, 'semantic_adapter', None)
        if semantic_session is not None:
            semantic_session.retirement_deselect_common_cv(button)
            return True
        count = 0
        RETIRE_COIN.load_color(self.device.image)
        RETIRE_COIN._match_init = True
        self.interval_clear(SHIP_CONFIRM_2)

        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            # End
            if not RETIRE_COIN.match(self.device.image, offset=(20, 20), similarity=0.97):
                return True
            if count > 3:
                logger.warning('_retire_select_one failed after 3 trial')
                return False

            if self.appear(SHIP_CONFIRM_2, offset=(30, 30), interval=2):
                self.device.click(button)
                count += 1
                continue


    def retirement_get_common_rarity_cv_in_page(self):
        """
            Returns:
                Button:
            """
        if self.config.GemsFarming_CommonCV == 'any':
            for common_cv_name in ['BOGUE', 'HERMES', 'LANGLEY', 'RANGER']:
                semantic_session = getattr(self.device, 'semantic_adapter', None)
                if semantic_session is not None:
                    button = semantic_session.retirement_match_common_cv(common_cv_name)
                    if button is not None:
                        return button
                    continue
                template = globals()[f'TEMPLATE_{common_cv_name}']
                sim, button = template.match_result(resize(self.device.image, size=(1189, 669)))
                if sim > self.config.COMMON_CV_THRESHOLD:
                    return Button(button=tuple((_ * 155 // 144 for _ in button.button)), area=button.area, color=button.color, name=f'TEMPLATE_{common_cv_name}_RETIRE')
            return None
        else:
            semantic_session = getattr(self.device, 'semantic_adapter', None)
            if semantic_session is not None:
                return semantic_session.retirement_match_common_cv(self.config.GemsFarming_CommonCV.upper())
            template = globals()[f'TEMPLATE_{self.config.GemsFarming_CommonCV.upper()}']
            sim, button = template.match_result(resize(self.device.image, size=(1189, 669)))
            if sim > self.config.COMMON_CV_THRESHOLD:
                return Button(button=tuple((_ * 155 // 144 for _ in button.button)), area=button.area, color=button.color, name=f'TEMPLATE_{self.config.GemsFarming_CommonCV.upper()}_RETIRE')
            return None


    def retirement_get_common_rarity_cv(self, skip_first_screenshot=False):
        """
        Args:
            skip_first_screenshot:

        Returns:
            Button: Button to click to remove ship from retire list
        """
        swipe_count = 0
        disappear_confirm = Timer(2, count=6)
        top_checked = False
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            # Try to get CV
            button = self.retirement_get_common_rarity_cv_in_page()
            if button is not None:
                return button

            # Wait scroll bar
            if RETIRE_CONFIRM_SCROLL.appear(main=self):
                disappear_confirm.clear()
            else:
                disappear_confirm.start()
                if disappear_confirm.reached():
                    logger.warning('Scroll bar disappeared, stop')
                    break
                else:
                    continue

            if not top_checked:
                top_checked = True
                logger.info('Find common CV from bottom to top')
                RETIRE_CONFIRM_SCROLL.set_bottom(main=self)
                continue
            else:
                if RETIRE_CONFIRM_SCROLL.at_top(main=self):
                    logger.info('Scroll bar reached top, stop')
                    break
                # Swipe prev page
                if swipe_count >= 7:
                    logger.info('Reached maximum swipes to find common CV')
                    break
                RETIRE_CONFIRM_SCROLL.prev_page(main=self)
                swipe_count += 1

        return button


    def keep_one_common_cv(self):
        """
        Returns:

        """
        from contextlib import nullcontext
        semantic_session = getattr(self.device, 'semantic_adapter', None)
        scope = (semantic_session.retirement_preconfirm_scope(RETIRE_CONFIRM_SCROLL)
                 if semantic_session is not None else nullcontext())
        with scope:
            logger.info('Keep one common CV')
            button = self.retirement_get_common_rarity_cv()
            if button is not None:
                self._retire_select_one(button)
                self._have_kept_cv = True
            logger.info('Keep one common CV end')


