"""
Background Workers Example

This demonstrates background task processing with asyncio.
Features shown:
- Background task processing with asyncio queues
- Service lifecycle (start/stop methods)
- Streaming responses from background workers
- Task status monitoring

Usage:
    python workers.py

Test with:
    curl http://localhost:8000/submit/urgent/process_data
    curl http://localhost:8000/submit/normal/backup_files
    curl http://localhost:8000/status
    curl http://localhost:8000/results  # SSE stream of completed tasks
"""

from typing import Optional, AsyncIterator
from extra import Service, HTTPRequest, HTTPResponse, on, expose, run
from extra.utils.logging import info
import asyncio
import time
import json


class WorkerService(Service):
	def __init__(self):
		super().__init__()
		self.task_queue: Optional[asyncio.Queue] = None
		self.result_queue: Optional[asyncio.Queue] = None
		self.worker_task: Optional[asyncio.Task] = None
		self.completed_tasks = []
		self.task_counter = 0

	async def start(self):
		"""Initialize queues and start background worker."""
		self.task_queue = asyncio.Queue()
		self.result_queue = asyncio.Queue()

		# Start background worker
		self.worker_task = asyncio.create_task(self._worker())
		info("Background worker started")

	async def stop(self):
		"""Stop background worker and cleanup."""
		if self.worker_task and not self.worker_task.done():
			self.worker_task.cancel()
			try:
				await self.worker_task
			except asyncio.CancelledError:
				pass
		info("Background worker stopped")

	async def _worker(self):
		"""Background worker that processes tasks from the queue."""
		info("Worker thread started")

		while True:
			try:
				# Get task from queue
				task = await self.task_queue.get()

				info(f"Processing task: {task['name']}")
				start_time = time.time()

				# Simulate work based on priority
				work_time = 1.0 if task["priority"] == "urgent" else 3.0
				await asyncio.sleep(work_time)

				# Create result
				result = {
					"task_id": task["id"],
					"name": task["name"],
					"priority": task["priority"],
					"duration": time.time() - start_time,
					"completed_at": time.time(),
					"status": "completed",
				}

				# Store result
				self.completed_tasks.append(result)
				await self.result_queue.put(result)

				info(f"Task completed: {task['name']} in {result['duration']:.2f}s")

				# Mark task as done
				self.task_queue.task_done()

			except asyncio.CancelledError:
				info("Worker cancelled")
				break
			except Exception as e:
				info(f"Worker error: {e}")

	@expose(POST="/submit/{priority:word}/{task_name:word}")
	async def submit_task(self, priority: str, task_name: str) -> dict:
		"""Submit a new task to the background worker."""
		if priority not in ["urgent", "normal"]:
			return {"error": "Priority must be urgent or normal"}

		self.task_counter += 1
		task = {
			"id": self.task_counter,
			"name": task_name,
			"priority": priority,
			"submitted_at": time.time(),
		}

		await self.task_queue.put(task)

		return {
			"status": "submitted",
			"task_id": task["id"],
			"position_in_queue": self.task_queue.qsize(),
		}

	@expose(GET="/status")
	async def get_status(self) -> dict:
		"""Get current worker status and queue information."""
		return {
			"queue_size": self.task_queue.qsize() if self.task_queue else 0,
			"completed_tasks": len(self.completed_tasks),
			"worker_running": self.worker_task and not self.worker_task.done(),
			"recent_completions": self.completed_tasks[-5:],  # Last 5 completed
		}

	@on(GET="/results")
	def stream_results(self, request: HTTPRequest) -> AsyncIterator[str]:
		"""Stream completed task results via Server-Sent Events."""

		async def stream():
			info("Client connected to results stream")

			# Send existing completed tasks first
			for result in self.completed_tasks[-3:]:  # Last 3 results
				yield f"data: {json.dumps(result)}\n\n"

			# Stream new results as they come
			while True:
				try:
					# Wait for new result with timeout
					result = await asyncio.wait_for(
						self.result_queue.get(), timeout=1.0
					)
					yield f"data: {json.dumps(result)}\n\n"
				except asyncio.TimeoutError:
					# Send keepalive
					yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': time.time()})}\n\n"
				except Exception as e:
					info(f"Stream error: {e}")
					break

		return request.onClose(lambda _: info("Results stream disconnected")).respond(
			stream(), contentType="text/event-stream"
		)


if __name__ == "__main__":
	info("Starting background worker service")
	info("Try these commands:")
	info("  curl -X POST http://localhost:8000/submit/urgent/important_task")
	info("  curl http://localhost:8000/status")
	info("  curl http://localhost:8000/results")
	run(WorkerService())

# EOF
