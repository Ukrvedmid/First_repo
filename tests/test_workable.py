import unittest

from app.sources import workable


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.requested_url = None

    def get(self, url, **kwargs):
        self.requested_url = url
        return _Response(self.payload)


class WorkableSourceTests(unittest.TestCase):
    def test_fetches_public_jobs_and_strips_html(self):
        session = _Session({
            'jobs': [
                {
                    'title': 'Technical Superintendent',
                    'shortcode': 'ABC123',
                    'shortlink': 'https://apply.workable.com/dof/j/ABC123/',
                    'location': {'location_str': 'Hamburg, Germany'},
                    'department': 'Marine',
                    'description': '<p>Chief Engineer with DP vessel experience.</p>',
                    'requirements': '<ul><li>Planned maintenance</li></ul>',
                }
            ]
        })

        jobs = workable.fetch(
            {'account': 'dof'},
            session,
            timeout=20,
            user_agent='test-agent',
        )

        self.assertEqual(
            session.requested_url,
            'https://www.workable.com/api/accounts/dof?details=true',
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['title'], 'Technical Superintendent')
        self.assertEqual(jobs[0]['location'], 'Hamburg, Germany')
        self.assertEqual(
            jobs[0]['url'],
            'https://apply.workable.com/dof/j/ABC123/',
        )
        self.assertIn('Hamburg, Germany', jobs[0]['description'])
        self.assertIn('Chief Engineer with DP vessel experience.', jobs[0]['description'])
        self.assertNotIn('<p>', jobs[0]['description'])

    def test_accepts_list_payload_and_builds_shortlink(self):
        session = _Session([
            {
                'title': 'ROV Pilot Technician',
                'shortcode': 'ROV456',
                'description': 'Offshore ROV maintenance',
            }
        ])

        jobs = workable.fetch(
            {'account': 'dof'},
            session,
            timeout=20,
            user_agent='test-agent',
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['location'], '')
        self.assertEqual(
            jobs[0]['url'],
            'https://apply.workable.com/dof/j/ROV456/',
        )


if __name__ == '__main__':
    unittest.main()
