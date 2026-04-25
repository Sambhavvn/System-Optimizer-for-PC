from __future__ import annotations
import multiprocessing as mp
import time

def _is_prime(n: int) -> bool:
    """Helper function to test if a number is prime."""
    if n <= 1:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True

class BenchmarkService:
    """Simple CPU benchmark that counts prime numbers per second."""

    def cpu_score(self, seconds: int = 10) -> int:
        """
        Measures system performance by calculating how many prime numbers
        the CPU can process per second using all cores.
        """
        start_time = time.monotonic()
        total_primes = 0
        number = 2

        with mp.Pool(processes=mp.cpu_count()) as pool:
            while time.monotonic() - start_time < seconds:
                numbers_to_test = list(range(number, number + 1000))
                results = pool.map(_is_prime, numbers_to_test)
                total_primes += sum(results)
                number += 1000

        return int(total_primes / seconds)
