CREATE TABLE IF NOT EXISTS retest_reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL,
    state ENUM('pending','retained','excluded') NOT NULL DEFAULT 'pending',
    note VARCHAR(240) NOT NULL,
    submitted_by VARCHAR(40) NOT NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decision_note VARCHAR(240),
    decided_by VARCHAR(40),
    decided_at TIMESTAMP NULL,
    original_state VARCHAR(16) NOT NULL,
    original_result JSON NOT NULL,
    original_note VARCHAR(240),
    final_state VARCHAR(16),
    final_result JSON,
    final_note VARCHAR(240),
    INDEX (task_id,state),
    FOREIGN KEY (task_id) REFERENCES outreach_tasks(id),
    FOREIGN KEY (submitted_by) REFERENCES staff(username),
    FOREIGN KEY (decided_by) REFERENCES staff(username)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS retest_superseded_windows (
    window_id INT PRIMARY KEY,
    review_id INT NOT NULL,
    FOREIGN KEY (window_id) REFERENCES sampling_windows(id),
    FOREIGN KEY (review_id) REFERENCES retest_reviews(id)
) CHARACTER SET utf8mb4;
