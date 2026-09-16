#!/usr/bin/env python3
"""Independent contract checks for the deterministic SDK contention holder."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdk_client


class Delta:
    def __init__(self, role): self.role = role
class Choice:
    def __init__(self, role): self.delta = Delta(role)
class Chunk:
    def __init__(self, role): self.choices = [Choice(role)]
class Stream:
    def __init__(self, chunks, error=None): self.chunks = chunks; self.error = error; self.closed = False
    def __iter__(self):
        for chunk in self.chunks: yield chunk
        if self.error: raise self.error
    def close(self): self.closed = True


class HolderContract(unittest.TestCase):
    def holder(self, stream):
        client = object()
        original = sdk_client.chat
        sdk_client.chat = lambda received, content, **kwargs: stream
        self.addCleanup(setattr, sdk_client, 'chat', original)
        holder = sdk_client.ContentionHolder(client)
        holder.start()
        return holder

    def test_delayed_before_admission_is_not_a_false_admission(self):
        stream = Stream([])
        holder = self.holder(stream)
        with self.assertRaisesRegex(AssertionError, 'before admission'):
            holder.await_admission(.2)

    def test_holder_failure_before_admission_surfaces(self):
        holder = self.holder(Stream([], RuntimeError('synthetic holder failure')))
        with self.assertRaisesRegex(AssertionError, 'RuntimeError'):
            holder.await_admission(.2)

    def test_admission_holds_until_explicit_release(self):
        stream = Stream([Chunk('assistant')])
        holder = self.holder(stream)
        holder.await_admission(.2)
        self.assertFalse(holder.finished.is_set())
        holder.close()
        self.assertTrue(stream.closed)

    def test_source_requires_exact_busy_shape_and_cleanup(self):
        text = (Path(__file__).parent / 'sdk_client.py').read_text()
        for required in [
            'holder.await_admission()',
            'except openai.RateLimitError as error:',
            'assert error.status_code == 429',
            'body.get("code") == "server_busy"',
            'body.get("type") == "rate_limit_error"',
            'holder released before contender response',
            'holder.close()',
        ]: self.assertIn(required, text)


if __name__ == '__main__': unittest.main()
