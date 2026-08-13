import unittest

from app.sources.crawl import _job_from_page


class _Response:
    def __init__(self, text):
        self.text = text


class CrawlLocationTests(unittest.TestCase):
    def test_extracts_jobposting_json_ld_location(self):
        response = _Response(
            '''
            <html>
              <head>
                <title>Technical Superintendent</title>
                <script type="application/ld+json">
                {
                  "@context": "https://schema.org",
                  "@type": "JobPosting",
                  "title": "Technical Superintendent",
                  "jobLocation": {
                    "@type": "Place",
                    "address": {
                      "@type": "PostalAddress",
                      "addressLocality": "Hamburg",
                      "addressRegion": "Hamburg",
                      "addressCountry": "DE"
                    }
                  }
                }
                </script>
              </head>
              <body><main><h1>Technical Superintendent</h1></main></body>
            </html>
            '''
        )

        job = _job_from_page('https://example.com/job/1', response)

        self.assertEqual(job['title'], 'Technical Superintendent')
        self.assertIn('Hamburg', job['location'])
        self.assertIn('DE', job['location'])

    def test_extracts_labelled_location(self):
        response = _Response(
            '''
            <html><body><main>
              <h1>Marine Service Engineer</h1>
              <p>Location: Kiel, Germany</p>
              <p>Commissioning of marine propulsion systems.</p>
            </main></body></html>
            '''
        )

        job = _job_from_page('https://example.com/job/2', response)

        self.assertIn('Kiel, Germany', job['location'])


if __name__ == '__main__':
    unittest.main()
