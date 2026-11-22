from fastapi import HTTPException

from src.contracts import TaskState
from src.fieldwork import current_point, get_point, get_task, required
from src.storage import encode, register

# A conclusion stays unrestored while its review is pending, or after exclusion
# until the supplementary retest is archived again (final_result recorded).
OPEN_REVIEW = "rr.state='pending' OR (rr.state='excluded' AND rr.final_result IS NULL)"


def open_review_clause(alias):
    """Point-level pause on rectification handoffs until the conclusion is restored."""
    return f'''NOT EXISTS (SELECT 1 FROM retest_reviews rr JOIN outreach_tasks rt ON rt.id=rr.task_id
        WHERE rt.point_id={alias}.point_id AND rt.state<>'obsolete' AND ({OPEN_REVIEW}))'''


def point_review_open(ledger, point_id):
    return ledger.one(f'''SELECT rr.id FROM retest_reviews rr JOIN outreach_tasks rt ON rt.id=rr.task_id
        WHERE rt.point_id=%s AND rt.state<>'obsolete' AND ({OPEN_REVIEW}) LIMIT 1''', (point_id,)) is not None


def attach_reviews(ledger, tasks):
    ids = tuple(task['id'] for task in tasks)
    if not ids:
        return tasks
    marks = ','.join(['%s'] * len(ids))
    reviews = ledger.rows(f'SELECT * FROM retest_reviews WHERE task_id IN ({marks}) ORDER BY id DESC', ids)
    for task in tasks:
        task['reviews'] = [review for review in reviews if review['task_id'] == task['id']]
    return tasks


def submit_review(task_id, form, actor):
    with register(write=True) as ledger:
        task = get_task(ledger, task_id)
        if task['state'] not in (TaskState.IMPROVED, TaskState.FOLLOWUP) or task['result'] is None:
            raise HTTPException(409, '仅已归档的复测结论可提交复核')
        current_point(get_point(ledger, task['point_id']), task['point_revision'])
        if ledger.one("SELECT id FROM retest_reviews WHERE task_id=%s AND state='pending' LIMIT 1", (task_id,)):
            raise HTTPException(409, '该复测结论已有复核在办')
        review_id = ledger.execute('''INSERT INTO retest_reviews
            (task_id,note,submitted_by,original_state,original_result,original_note) VALUES (%s,%s,%s,%s,%s,%s)''',
            (task_id, form.note, actor, task['state'], encode(task['result']), task['review_note']))
        ledger.audit(actor, 'retest_review_submitted', review_id, {'task_id': task_id, 'note': form.note})
        return {'id': review_id, 'state': 'pending'}


def decide_review(review_id, form, actor):
    with register(write=True) as ledger:
        review = required(ledger, 'SELECT * FROM retest_reviews WHERE id=%s', review_id, '复测复核单')
        if review['state'] != 'pending' or review['submitted_by'] == actor:
            raise HTTPException(409, '需由另一名运营账号裁定待处理复核')
        task = get_task(ledger, review['task_id'])
        if task['state'] not in (TaskState.IMPROVED, TaskState.FOLLOWUP) or task['result'] is None:
            raise HTTPException(409, '任务结论已变化，无法裁定该复核')
        if form.decision == 'excluded':
            current_point(get_point(ledger, task['point_id']), task['point_revision'])
        ledger.execute('''UPDATE retest_reviews SET state=%s,decision_note=%s,decided_by=%s,decided_at=NOW()
            WHERE id=%s''', (form.decision, form.note, actor, review_id))
        facts = {'task_id': task['id'], 'state': form.decision, 'note': form.note}
        if form.decision == 'excluded':
            window_ids = task['result']['window_ids']
            for window_id in window_ids:
                ledger.execute('INSERT INTO retest_superseded_windows (window_id,review_id) VALUES (%s,%s)',
                               (window_id, review_id))
            ledger.execute('DELETE FROM retest_appointments WHERE task_id=%s', (task['id'],))
            ledger.execute("UPDATE outreach_tasks SET state='retesting',result=NULL,review_note=NULL WHERE id=%s",
                           (task['id'],))
            facts['superseded_window_ids'] = window_ids
        ledger.audit(actor, 'retest_review_decided', review_id, facts)
        return {'id': review_id, 'state': form.decision}
