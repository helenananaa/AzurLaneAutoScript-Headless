def _storage_disassemble_equipment_execute_once(self, amount=40):
        """
        Returns:
            int: amount of equipments disassembled

        Pages:
            in: DISASSEMBLE_CANCEL
            out: DISASSEMBLE_CANCEL
        """
        success = False
        amount = min(amount, 40)
        self.interval_clear([
            DISASSEMBLE_CONFIRM,
            DISASSEMBLE_POPUP_CONFIRM,
            GET_ITEMS_1,
            GET_ITEMS_2,
            DISASSEMBLE_CANCEL,
        ])
        logger.info(f'Disassemble once, expected amount: {amount}')

        for _ in self.loop():
            if self.appear(GET_ITEMS_1, offset=(5, 5), interval=3):
                logger.info(f'{GET_ITEMS_1} -> {DISASSEMBLE_CONFIRM}')
                self.device.click(DISASSEMBLE_CONFIRM)
                continue
            if self.appear(GET_ITEMS_2, offset=(5, 5), interval=3):
                logger.info(f'{GET_ITEMS_2} -> {DISASSEMBLE_CONFIRM}')
                self.device.click(DISASSEMBLE_CONFIRM)
                continue
            if self.handle_info_bar():
                continue
            if self.appear(DISASSEMBLE_CANCEL, offset=(20, 20)):
                break
        self.interval_clear([
            GET_ITEMS_1,
            GET_ITEMS_2,
        ])
        self.wait_until_stable(MATERIAL_STABLE_CHECK)

        items = EQUIPMENT_ITEMS.predict(self.device.image, name=False, amount=True)
        if not len(items):
            logger.warning('No items in storage to disassemble')
            return 0
        cumsum = np.cumsum([item.amount for item in items])
        for item, total in zip(items, cumsum):
            if item.amount <= 0:
                continue
            self.device.click(item)
            self.device.click_record.pop()
            if total >= amount:
                amount = total
                break
        amount = min(cumsum[-1], amount)

        # Wait items being selected
        logger.info(f'Disassemble once, in_storage amount: {amount}')
        timeout = Timer(1, count=2).start()
        prev_disassemble = 0
        while 1:
            self.device.screenshot()
            disassembled = OCR_DISASSEMBLE_COUNT.ocr(self.device.image)
            if disassembled >= amount:
                logger.info('Disassemble amount reached expected amount')
                break
            if timeout.reached():
                logger.warning('Wait disassemble amount timeout')
                break
            if disassembled > prev_disassemble:
                prev_disassemble = disassembled
                timeout.reset()

        logger.info(f'Disassemble once, actual amount: {disassembled}')
        if disassembled <= 0:
            logger.warning('No items selected to disassemble')
            return 0

        skip_first_screenshot = True
        click_count = 0
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if click_count >= 3:
                # Probably because no item is selected,
                # _storage_disassemble_equipment_execute() will retry selecting
                logger.warning('Failed to confirm disassemble after 3 trial')
                disassembled = 0
                break
            if success and self.appear(DISASSEMBLE_CANCEL, offset=(20, 20)):
                self.wait_until_stable(MATERIAL_STABLE_CHECK)
                break

            if self.appear_then_click(DISASSEMBLE_CONFIRM, offset=(20, 20), interval=5):
                click_count += 1
                continue
            if self.appear_then_click(DISASSEMBLE_POPUP_CONFIRM, offset=(-15, -5, 5, 70), interval=5):
                # since 2025.05.20 disassemble no longer shows GET_ITEMS
                success = True
                continue
            if self.handle_popup_confirm('DISASSEMBLE'):
                continue
            if self.appear(GET_ITEMS_1, offset=(5, 5), interval=3):
                logger.info(f'{GET_ITEMS_1} -> {DISASSEMBLE_CONFIRM}')
                self.device.click(DISASSEMBLE_CONFIRM)
                success = True
                continue
            if self.appear(GET_ITEMS_2, offset=(5, 5), interval=3):
                logger.info(f'{GET_ITEMS_2} -> {DISASSEMBLE_CONFIRM}')
                self.device.click(DISASSEMBLE_CONFIRM)
                success = True
                continue

        return disassembled
