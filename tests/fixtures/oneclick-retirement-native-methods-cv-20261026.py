"""Exact native whole one-click method with conditional CV protection hook."""
class Retirement:
    def retire_ships_one_click(self):
            from alas_headless import current_semantic_session, SemanticGateClosed
            semantic_session = current_semantic_session()
            if semantic_session is not None:
                if self.retire_keep_common_cv:
                    cv_policy = getattr(semantic_session, 'require_common_cv_retirement_protection', None)
                    if not callable(cv_policy):
                        raise SemanticGateClosed('retirement common-CV preservation port is unavailable')
                    cv_policy()
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
