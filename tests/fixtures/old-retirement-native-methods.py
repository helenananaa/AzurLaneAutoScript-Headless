"""Exact staged native methods; original ALAS owns loops and decisions."""
class Retirement:
    def _retirement_choose(self, amount=10, target_rarity=('N',)):
        """
        Args:
            amount (int): Amount of cards retire. 0 to 10.
            target_rarity (tuple(str)): Card rarity. N, R, SR, SSR.

        Returns:
            int: Amount of cards have retired.
        """
        semantic_session = getattr(self.device, 'semantic_adapter', None)
        if semantic_session is not None:
            cards, rarity = semantic_session.old_retirement_card_vectors(
                target_rarity=target_rarity,
                card_limit=int(CARD_RARITY_GRIDS.grid_shape[0]) * int(CARD_RARITY_GRIDS.grid_shape[1]))
        else:
            cards = []
            rarity = []
            for x, y, button in CARD_RARITY_GRIDS.generate():
                card_color = get_color(image=self.device.image, area=button.area)
                f = False
                for r, rarity_color in CARD_RARITY_COLORS.items():

                    if color_similar(card_color, rarity_color, threshold=15):
                        cards.append([x, y])
                        rarity.append(r)
                        f = True

                if not f:
                    logger.warning(
                        f'Unknown rarity color. Grid: ({x}, {y}). Color: {card_color}')

            logger.info(' '.join([r.rjust(3) for r in rarity[:7]]))
            logger.info(' '.join([r.rjust(3) for r in rarity[7:]]))

        selected = 0
        for card, r in zip(cards, rarity):
            if r in target_rarity:
                if semantic_session is not None:
                    semantic_session.old_retirement_select_card(card)
                else:
                    self.device.click(CARD_GRIDS[card])
                self.device.sleep((0.1, 0.15))
                selected += 1
            if selected >= amount:
                break
        return selected

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
            semantic_session.require_old_retirement_policy(keep_common_cv=self.retire_keep_common_cv)
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
