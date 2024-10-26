from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl, Field
import requests
import os
import logging
import redis
from dotenv import load_dotenv
import re

load_dotenv()

redis_client = redis.StrictRedis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=0,
    decode_responses=True
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI()


for var in ['GITHUB_TOKEN', 'OPENAI_API_KEY']:
    if not os.getenv(var):
        logger.error(f"Missing {var} in environment variables!")
        

class UserValue(BaseModel):
    assignment_description: str = Field(..., min_length=5, max_length=500, description="A brief description of the assignment")
    github_url: HttpUrl = Field(..., description="A valid GitHub URL for the repository to review")
    user_level: str = Field(..., pattern=r'^(junior|mid|senior)$', description="User level can be 'junior', 'mid', or 'senior'")


class Review(BaseModel):
    files: list[str] = []
    downsides_comments: str = None
    rating: str = None
    conclusion: str = None

    def analyze_files(self, gpt_response: str):
        try:
            # Find the start index of each section in the GPT response
            downsides_start = gpt_response.find("**Downsides/Comments**")
            rating_start = gpt_response.find("**Rating**")
            conclusion_start = gpt_response.find("**Conclusion**")
            
            # Extract Downsides/Comments
            if downsides_start != -1 and rating_start != -1:
                downsides_start += len("**Downsides/Comments**") + 1  # Move to the end of the header
                self.downsides_comments = gpt_response[downsides_start:rating_start].strip()
            else:
                self.downsides_comments = "Downsides/Comments section not found."
            
            # Extract Rating
            if rating_start != -1 and conclusion_start != -1:
                rating_start += len("**Rating**") + 1 # Move to the end of the header
                self.rating = gpt_response[rating_start:conclusion_start].strip()
            else:
                self.rating = "Rating section not found."
            
            # Extract Conclusion
            if conclusion_start != -1:
                conclusion_start += len("**Conclusion**") + 1 # Move to the end of the header
                self.conclusion = gpt_response[conclusion_start:].strip()
            else:
                self.conclusion = "Conclusion section not found."
            

        except Exception as e:
            logger.error(f"Error parsing GPT response: {e}")
            self.downsides_comments, self.rating, self.conclusion = "Parsing error", "N/A", "Parsing error"

    def create_review(self, gpt_response: str) -> dict:
        self.analyze_files(gpt_response)
        return {
            "found_files": self.files,
            "downsides_comments": self.downsides_comments,
            "rating": self.rating,
            "conclusion": self.conclusion
        }


def valid_github_url(url: str) -> bool:
    pattern = r"^https:\/\/github\.com\/[\w-]+\/[\w-]+$"
    logger.info(re.match(pattern, str(url)) is not None)
    return re.match(pattern, str(url)) is not None


def get_github_repo_contents(owner: str, repo: str, path=''):
    logger.info(f"Fetching contents from GitHub repo: {owner}/{repo}/{path}")
    api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{path}'
    headers = {
        'Authorization': f'token {os.getenv("GITHUB_TOKEN")}',
        'Accept': 'application/vnd.github.v3+json'
    }
    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            contents = response.json()
            all_files = []
            for item in contents:
                if item['type'] == 'file':
                    file_content = fetch_file_content(owner, repo, item['path'])
                    if file_content:
                        all_files.append({"path": item['path'], "content": file_content})
                elif item['type'] == 'dir':
                    all_files.extend(get_github_repo_contents(owner, repo, item['path']))
            return all_files
        else:
            logger.error(f"Error fetching repo contents: {response.status_code} - {response.json()}")
            return None
    except Exception as e:
        logger.error(f"Exception while fetching GitHub repo contents: {e}")
        return None
    

def fetch_file_content(owner: str, repo: str, file_path: str) -> str:
    file_api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{file_path}'
    headers = {
        'Authorization': f'token {os.getenv("GITHUB_TOKEN")}',
        'Accept': 'application/vnd.github.v3.raw'
    }
    response = requests.get(file_api_url, headers=headers)
    if response.status_code == 200:
        return response.text
    else:
        logger.error(f"Failed to fetch file content for {file_path}: {response.status_code}")
        return None


def fetch_file_content(owner: str, repo: str, file_path: str) -> str:
    file_api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{file_path}'
    headers = {
        'Authorization': f'token {os.getenv("GITHUB_TOKEN")}',
        'Accept': 'application/vnd.github.v3.raw'
    }
    response = requests.get(file_api_url, headers=headers)
    if response.status_code == 200:
        return response.text
    else:
        logger.error(f"Failed to fetch file content for {file_path}: {response.status_code}")
        return None



@app.post("/review")
async def review_code(request_body: UserValue):

    if not valid_github_url(request_body.github_url):
        logger.error("Invalid GitHub URL provided")
        raise HTTPException(status_code=400, detail="Invalid GitHub URL. Please provide a valid repository link.")
    cache_key = f"review:{request_body.github_url}:{request_body.user_level}:{request_body.assignment_description}"
    cached_response = redis_client.get(cache_key)
    if cached_response:
        logger.info("Returning cached review")
        return JSONResponse(content=eval(cached_response))
    
    parts = str(request_body.github_url).split('/')
    owner, repo = parts[-2], parts[-1]
    contents = get_github_repo_contents(owner, repo)

    if not contents:
        logger.error("Failed to retrieve GitHub contents")
        raise HTTPException(status_code=500, detail="Could not retrieve GitHub repository contents.")

    review = Review(files=[file['path'] for file in contents])
    gpt_response = await get_review(contents, request_body.user_level, request_body.assignment_description)
    review_data = review.create_review(gpt_response)

    redis_client.setex(cache_key, 86400, str(review_data))
    return review_data


async def get_review(files: list[dict], user_level: str, assignment_description: str) -> str:
    api_key = os.getenv('OPENAI_API_KEY')
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    file_descriptions = "\n".join(
        f"**File**: {file['path']}\n**Content**:\n{file['content']}"
        for file in files
    )
    instructions = f"""
    You are a code review assistant. Your task is to review the code from the following files based on the assignment description provided below. It is **crucial** that your feedback strictly follows the specified format outlined below:

    **Assignment Description**: {assignment_description}

    **Files**:
    {file_descriptions}

    **User Level**: {user_level}

    **Feedback Structure** (respond **exactly** in this format):
    - **Downsides/Comments**: Identify issues and provide suggestions for improvement.
    - **Rating**: Should be in format x/10 where x is your grade
    - **Conclusion**: Summarize your overall feedback.

    Please ensure that your response is **detailed**, **constructive**, and adheres **exactly** to this structure. Responses that do not follow this format will not be accepted.
    """



    data = {
        "model": "gpt-4-turbo",
        "messages": [
            {"role": "system", "content": "You are a code review assistant."},
            {"role": "user", "content": instructions}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            logger.info("Review generated successfully.")
            return response.json()['choices'][0]['message']['content']
        else:
            logger.error(f"Failed to generate review: {response.status_code} - {response.text}")
            return "Review generation failed."
    except Exception as e:
        logger.error(f"Error while generating review: {e}")
        return "Review generation failed."
