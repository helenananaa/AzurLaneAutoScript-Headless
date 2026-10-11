"""Plain receipt for one explicitly approved food purchase, across reloads."""
import json
import os
from pathlib import Path
from datetime import datetime
from .contracts import AlasSemanticActionDeferred

AUTH_ENV = 'ALAS_SEMANTIC_DORM_FOOD_PURCHASE_AUTHORIZATION'


def _save(path, record):
    try:
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except OSError as exc:
        raise AlasSemanticActionDeferred('Dorm food authorization receipt is not writable') from exc


def purchase_food_once(proposal, stock_before, operation, dispatch_count):
    value = os.environ.get(AUTH_ENV)
    if not value:
        raise AlasSemanticActionDeferred(
            'Dorm food purchase awaits explicit authorization: '
            f'{proposal.quantity} x {proposal.food_name}, total={proposal.total_cost}, '
            f'currency_sprite={proposal.currency_sprite}, item_sprite={proposal.item_sprite}')
    path = Path(value)
    try:
        record = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise AlasSemanticActionDeferred('Dorm food authorization receipt is unavailable') from exc
    if (record.get('state') != 'approved' or record.get('quantity') != proposal.quantity
            or record.get('food_name') != proposal.food_name
            or record.get('currency_sprite') != proposal.currency_sprite
            or record.get('item_sprite') != proposal.item_sprite
            or not isinstance(record.get('max_total_cost'), int)
            or not 0 <= proposal.total_cost <= record['max_total_cost']):
        raise AlasSemanticActionDeferred('Dorm food quote is outside the unused one-purchase authorization')
    before = dispatch_count()
    record.update(state='reserved', reserved_at=datetime.now().astimezone().isoformat(),
                  stock_before=stock_before, input_generation=proposal.generation,
                  actual_total_cost=proposal.total_cost)
    _save(path, record)
    try:
        receipt = operation()
    except Exception as exc:
        record.update(state='approved' if dispatch_count() == before else 'input-uncertain',
                      error=dict(type=type(exc).__name__, message=str(exc)))
        _save(path, record)
        raise
    record.update(state='dispatched', input_generation=receipt.generation,
                  input_path=receipt.path, input_point=dict(x=receipt.point.x, y=receipt.point.y))
    _save(path, record)
    return receipt


def note_food_purchase_result(feed, generation):
    """Record original ALAS' observed Feed return; do not choose or retry work."""
    value = os.environ.get(AUTH_ENV)
    if not value:
        return
    path = Path(value)
    try:
        record = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return
    if record.get('state') != 'dispatched' or generation <= record['input_generation']:
        return
    items = [item for item in feed.items if item.item_id == 50004]
    if len(items) == 1 and items[0].count == record['stock_before'] + record['quantity']:
        record.update(state='confirmed', post_generation=generation, stock_after=items[0].count,
                      confirmed_at=datetime.now().astimezone().isoformat(),
                      postcondition='Original ALAS observes uncovered Feed with curry inventory increased by authorized quantity')
        _save(path, record)
