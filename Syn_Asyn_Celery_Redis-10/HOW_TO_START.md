Go to the Syn-Async folder

run step by step and verify the results 


docker compose up --build

curl -s http://localhost:8000/health/live

curl -s http://localhost:8000/health/ready

python scripts/demo_full_flow.py


last check the Swagger part 

http://localhost:8000/docs



