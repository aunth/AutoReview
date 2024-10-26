

Task1




Task2
With the intention of scaling the FastAPI application for 100+ incoming review requests per minute and repos with more than a hundred files, I would employ a microservices architecture with asynchronous processing. Each review request would be such that there will be separate queues (e.g., RabbitMQ or Apache Kafka) that would be used to receive incoming requests from processing, so that horizontal scalability can be achieved for the worker services that conduct the reviews. In terms of storage of persistent data, I would deploy a mix of PostgreSQL (for structured data) and MongoDB (for semi-structured data), which would enable flexible management of user requests and responses. Redis would be employed as the caching layer with the aim of cutting the database load and increasing the response time for the most frequent queries. In terms of traffic dispersion, an API gateway (say NGINX or AWS API Gateway) would be utilized to receive the requests, apply rate limits and direct traffic to the relevant service.

Because of the rising adoption of OpenAI and GitHub APIs usage in parallel with the threat of their rate limits and associated costs, I would deploy a backoff strategy for the retries and queue review requests when the limits are streamed. I would deploy tools monitoring also other statistical usage to generate optimized requests, combining file content requests to GitHub and summarizing file contents during delivery to OpenAI, to cut on the number of API calls. Regular cost assessments and budget alerts would help manage expenses effectively as usage scales up. Additionally, using API proxies or rate-limiting tools could help balance the load and ensure compliance with API constraints