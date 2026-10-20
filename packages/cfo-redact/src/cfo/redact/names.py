"""Bundled Indian given names and surnames, lowercase.

A word on these lists is replaced with [REDACTED] inside a narration. The lists are meant to
be broad but never to hold merchant words, so the tests pin that brands such as Swiggy,
Zomato, Amazon and Ola stay readable. Anything missing here can be added by the owner as a
redaction term in the cockpit.
"""

GIVEN_NAMES = frozenset(
    """
aarav aarti aashish aditi aditya agastya ajay ajit akash akhil akshay alok aman amar amit amita
amol amrita anand ananya anil anirudh anita anjali ankit ankita anmol anup anupam anuradha anurag
aparna arjun arun aruna arvind asha ashish ashok ashwin atul avinash ayush bharat bhavna bhavya
bhuvan bimal binod biswajit chandan chandra chetan darshan deepa deepak deepika dev devika dhruv
dilip dinesh divya durga farhan gaurav gautam geeta gita girish gopal govind gunjan hari harish
harsh harshit hemant himanshu indira isha ishaan ishan ishita jagdish jai jaideep jatin jaya
jayesh jyoti kabir kailash kajal kamal kamla kanika karan karthik kavita kavya keshav kiran kiran
kishore komal krishna kriti kunal lakshmi lalit lata lavanya madhav madhu mahesh mahendra manish
manisha manoj mayank meena meera mehul mohan mohit mukesh mukul nagesh naman nandini narendra
naresh navin neeraj neha nidhi nikhil nikita nilesh nirmala nisha nitin nitish om pallavi pankaj
parth parvati pooja poonam prabhat pradeep pranav prashant pratik pratima preeti prem priya
priyanka puneet pushpa radha rahul raj rajan rajat rajeev rajendra rajesh rajiv rakesh ramesh
ranjana ranjit rashmi ravi rekha renu rishabh ritesh rohan rohit roshan ruchi rupa sachin sagar
sahil sai sakshi sameer sandeep sangeeta sanjay sanjana sanjeev sarita saurabh savita seema shailesh
shalini shankar sharad shashi shekhar shilpa shivam shreya shruti shubham siddharth smita sneha
sonal sonia sudhir suhas sumit sunil sunita suraj suresh sushil swati tanvi tarun tushar uday
uma umesh vaibhav vandana varun vedant vidya vijay vikas vikram vimal vinay vinod vipin vishal
vishnu vivek yash yogesh zoya
abhay abhishek achal advait aishwarya akansha alka amrit anamika anand anju ankush anshul anushka arnav arpita aryan ashima ashutosh atharv avni ayaan bhagat bhavesh bhavik bhumika chaitanya chhaya chirag daksh damini deepali devansh dhara dharmesh diksha dipak disha divyanshu eshan esha falguni ganesh garima gayatri gitanjali gokul govinda hardik hema hiten hrithik indu ira jahnavi janhvi jasmine jayant jignesh juhi kalpana kamini kamlesh kanchan kartik kaushal kavish keerthi ketan khushi kirti kishan kshitij kunj laxmi lokesh madhavi mahima malini manan mansi mayur mira mitali mitul mohini mrunal nakul namrata nandan natasha navya nayan neelam neelima nirav nirmal nishant nupur omkar paras parul payal pooja pragya prakash pranali pranjal prasad pratibha prerna pulkit purvi radhika rajni rakshit ramya rashi ritika ritu riya rohini ruchika sachi sakshi samar samir sanchit sandhya sangita sanket sapna sarika satish saumya shaan shalu sharmila shashank shefali shiv shobha shweta siddhi simran sitara sneh soham somesh sonali sourav sridhar srishti subhash sudha sujata sukanya sumedh sunanda supriya surbhi swarna tamanna tanuja tara tejas trisha tulsi urvashi utkarsh vaishali vandita vanya varsha vasudha vedika veena venkat vibha vidhi vihaan vinita vipul vrinda yamini yashika yatin yuvraj zara
""".split()
)

SURNAMES = frozenset(
    """
agarwal aggarwal ahuja anand arora bajpai banerjee bansal bhat bhatt bhatia chatterjee chauhan
chopra das desai deshmukh dubey dwivedi garg ghosh gill goel gupta iyer iyengar jain jha joshi
kapoor kapur kaul khan khanna kulkarni kumar malhotra malik mehra mehta menon mishra mukherjee
nair nambiar narayan pandey pandit patel pathak pillai pramanik rao rastogi reddy roy saxena sen
sengupta seth shah sharma shetty shukla singh sinha srivastava tandon thakur tiwari trivedi
tripathi varma verma yadav
acharya adhikari bhardwaj bhowmik biswas bose chakraborty chaudhary chowdhury dalal dhawan dixit doshi dutta gandhi ganguly goyal grover handa jaiswal kamath kaushik khatri kohli kothari lal mahajan mandal mathur mittal mondal nagar naidu narula oberoi pal pandya parekh pramanik puri raman rathore sagar sahu sanyal sarkar sethi shenoy shrivastava solanki subramanian suri swamy tomar upadhyay vaidya vyas wadhwa
""".split()
)

NAMES = GIVEN_NAMES | SURNAMES
