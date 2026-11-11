1
00:00:00,590 --> 00:00:01,250
Speaker 1: All right.

2
00:00:01,790 --> 00:00:06,150
Speaker 2: Um, cool. I guess we can just ask about questions then.

3
00:00:06,650 --> 00:00:08,250
Speaker 1 [uncertain]: All right. Um,

4
00:00:09,670 --> 00:00:46,410
Speaker 2: yeah, so you said for, I think it was question, uh, our first question, I think, let me just pull this up. Um, you said the target that we should be kind of setting. Um, this is for, yeah, question one, you said around 50 meters for around like two minutes would be a decent target I have. Um, we're kind of setting ourselves up for the 20, like a 25 meters for around five minutes. Like that's kind of like the drift we're aiming for. Um, would you rather see us like clearly beat 50 or with like a solid explanation of how we do it? Or should we like try and push for

5
00:00:46,410 --> 00:00:51,170
Speaker 1 [uncertain]: the stricter one? Solid, the, the, the rationale, the rationale important

6
00:00:55,560 --> 00:00:59,900
Speaker 2: as the result. Okay. The rationale is important as a result. Fair enough. Yeah. Yeah. need to

7
00:00:59,900 --> 00:01:06,060
Speaker 1: explain what you did, what you did, uh, how you did and, and why.

8
00:01:06,960 --> 00:01:21,720
Speaker 2: Yeah. I was about to ask you, um, like calculations for our confidence and like our drifts as well. Um, is it like, like a breakdown of like where each bit of error comes from? Like how it grows over time? Is that like kind of what you guys are looking for specifically? Or is there anything else that I'm like, not like, Yeah.

9
00:01:21,940 --> 00:01:40,480
Speaker 1: Yeah. Yeah. What, what are your calculation? What are the drifts? How you, you compensate or try to compensate? Right. Why, or, or how you determine or calculate that, uh, it would take X amount or minutes to get to that drift? Yeah. That kind of thing.

10
00:01:40,760 --> 00:02:18,880
Speaker 2: Fair enough. All right. Thanks. Um, yeah. I, I do gotta ask. We, so we're doing part of it in like real life and we're doing part of it in simulation cause, cause we don't have this hardware for some stuff in like real life. Um, we actually spent today like getting real tower and plane signals. Like, so cell towers and planes that are like overhead, but we only really have two to three towers in range at ground level. But we, we kind of need like four in range to like start using the towers as a primary signal. Um, like do the, would the judging give weight to like real recordings versus simulation? Like how would that kind of work? Would you guys like kind of look at the kind of the same as long as the simulator is grounded in reality?

11
00:02:27,840 --> 00:02:29,820
Speaker 1: It's okay. Well, uh, will have

12
00:02:46,400 --> 00:02:49,140
Speaker 1: 100% measurement. Uh,

13
00:02:51,390 --> 00:03:07,730
Speaker 1: I mean, it's preferred and it will be a good foundation to your, to your test, but, uh, try to understand that you have the logic of what you want to achieve. And by the way, why three towers won't be enough? Um,

14
00:03:08,510 --> 00:03:38,090
Speaker 2: basically what we're doing is we're trying to figure out like the third tower. We only really have two, but like the third tower is super weak. So we can't even use it as a real signal to like localize off of, which is why we were kind of going for a fourth, but it's really much more of a, if we didn't have enough towers, would you still be looking at the simulation? As long as the simulation itself is grounded, like with the logic itself is enough kind of thing, like, or do you guys really just are looking like that's what I, but you already answered the question. It's very much as long as the logic's there. Yeah.

15
00:03:38,890 --> 00:03:47,990
Speaker 1: Yeah. And I, have, and I have a question. Yeah. Um, can you, how can you identify between the towers?

16
00:03:48,770 --> 00:04:16,850
Speaker 2: The towers. Okay. So there are published, there's a, there was a public dataset that we found basically, um, all the carriers in the area, we found a dataset where they publish like the specific bands. They like have, um, like they transmit up and we're able to just define like, like we're able to, first of all, see the towers that we're going at. We can't see their exact location, obviously, but we can see the towers we're pinging and we can see what the network they're a part of. So who actually built them as well.

17
00:04:19,880 --> 00:04:24,200
Speaker 2: So like, example, like, um, the telos network versus the Roger network, that kind of thing.

18
00:04:27,620 --> 00:04:28,420
Speaker 1: And, and

19
00:04:31,110 --> 00:04:33,430
Speaker 1: how do you know where the telos is located?

20
00:04:33,830 --> 00:05:05,190
Speaker 2: Um, we don't know exactly. That's not, that's not a part of our dataset. just look at the single strength and we use that to figure out how far away we are from them. And then the public dataset we have tells us which towers are there. So if we're like in an area where we don't know where the towers are at, that's where this kind of like, kind of starts to break apart. But that's, we're still trying to figure that out. That's yeah. At least in Ottawa, because we're doing it for Ottawa right now. Like, like that's what we're kind of focusing on that. That's, uh, we just know the towers because of a dataset online.

21
00:05:07,030 --> 00:05:47,010
Speaker 2: Okay. Um, we don't know exactly how many, we don't know like where they're at. But we generally have a general idea and that's what we're using, at least for now. yeah, honestly, like a lot of our, like yesterday we spent just getting the simulator up and running. So like, like working well and like using that to like finally like get some tests through. So we're finally like looking into like the actual methods we want to use to localize. That's something we're still working on. Um, the first idea we had was to use the towers and kind of just like estimate the, the, the clock. Drift that they have. But, um, obviously that only really happens while you're in range with them. Um,

22
00:05:48,570 --> 00:05:49,090
Speaker 1: yeah, I,

23
00:05:49,410 --> 00:06:03,110
Speaker 2: I guess moving on, um, let's say like, uh, for Honeywell specifically, let's say like a pilot or like an operator sees a conference number. Like how does Honeywell normally like show it? we kind of want to like replicate that for our, like our platform. To

24
00:06:17,290 --> 00:06:35,530
Speaker 1: determine to what he will, he will, he will get. You can, you can select, uh, let's say, uh, maybe a heat map or green is absolute competent and red. Uh, you might don't want to print or lose. Okay. Okay.

25
00:06:38,360 --> 00:06:52,980
Speaker 2: Yeah. Heat map. All right. nothing specific. That's fair. Um, yeah. So for our risk level, like our, like for our, confidence number, we're doing, uh, we're using a one in 10 million with it. I, which I kind of see, like I saw, yo Ethan,

26
00:06:56,140 --> 00:06:58,200
Speaker 2: uh, we're on call with the guy. He's to say hi. Oh,

27
00:06:59,320 --> 00:06:59,580
Speaker 1: hello.

28
00:07:01,560 --> 00:07:02,860
Speaker 1: Hello. Yeah.

29
00:07:04,060 --> 00:07:08,720
Speaker 2: Yeah. Um, we're, we're kind of stuck in his basement right now. We're having a drone printed. Um,

30
00:07:09,320 --> 00:07:09,720
Speaker 1: so

31
00:07:09,720 --> 00:07:21,160
Speaker 2: we're using a one in 10 million risk level for our confidence number, which when I, I kind of read online, which was like aviation style. Is that like the right ballpark to have? Or do you guys do something different? He

32
00:07:23,240 --> 00:07:24,920
Speaker 1: was saying one to 10 million.

33
00:07:25,040 --> 00:07:31,700
Speaker 2: One in 10 million. So for our confidence number, here, let me pull up the specifics. Just give me one second. Um,

34
00:07:36,550 --> 00:07:43,770
Speaker 2: just give me one second. Sorry. I'm trying to, this isn't, this wasn't me. This was Mal, but he's actively working on something.

35
00:07:46,640 --> 00:07:47,000
Speaker 1 [uncertain]: Um,

36
00:07:48,280 --> 00:08:06,020
Speaker 2: you know what? While I look for that, well, I'll, I'll, come back to it later. I'll give you a more specific, uh, I'm just looking for that. Um, I, I'll look into, uh, we were also like looking into satellites. I'll, I'll, I'll come back to that. We were looking into satellites, like, uh, the Iridium network and the Starlink network, which set their clock from GPS. Um,

37
00:08:07,060 --> 00:08:07,620
Speaker 1: like if

38
00:08:07,620 --> 00:08:12,680
Speaker 2: the GPS is fake, like, would their timing be affected? Like, do you have any like experience with that?

39
00:08:14,120 --> 00:08:15,240
Speaker 1: They have a...

40
00:08:18,380 --> 00:08:26,500
Speaker 1 [uncertain]: I'm sorry. I couldn't hear you. Independent. Those networks have an independent timing source. Okay.

41
00:08:26,680 --> 00:08:30,960
Speaker 2: have an independent timing source. That's correct. That's actually works perfect. Um,

42
00:08:32,900 --> 00:08:51,660
Speaker 2: yeah, just following on that, like we were thinking like for a terminal that like loses GPS, that like a satellite terminal that uses GPS. We were thinking like, in terms of how accurate the clock needs to say, we were thinking like one point, like, like the margin is going to be like really tight. Like maybe after 10 minutes, we're like just around 1.5 microseconds. We didn't want to like...

43
00:08:51,660 --> 00:08:54,820
Speaker 1: You need, you need to be focused on,

44
00:08:58,180 --> 00:08:59,660
Speaker 1: you can second

45
00:09:03,690 --> 00:09:05,690
Speaker 1: priority. Okay. All right.

46
00:09:15,030 --> 00:09:19,190
Speaker 1: So, uh, try to refocus on the location itself.

47
00:09:19,610 --> 00:09:22,030
Speaker 2 [uncertain]: The location. All right. Yeah. No, it's just, okay. And less,

48
00:09:22,150 --> 00:09:23,910
Speaker 1: and less the timing.

49
00:09:24,750 --> 00:09:27,750
Speaker 2: All right. Fair. Fair enough. Um,

50
00:09:30,500 --> 00:09:33,440
Speaker 2: all right. Sorry. I'm just like reading through the rest of the questions written down. Um,

51
00:09:39,650 --> 00:10:02,070
Speaker 2: yeah, guess this would be a good question as well. Like, um, so when GPS, like I'm just asking like a situation, like I'm just trying to figure out what to design for here, but let's say the GPS goes out, like how long realistically would, would it be available before it's lost? Like, like, are we talking about like minutes or like a full, like, like the seconds, like, or can you just expect it to like, not be available for like a good duration of the flight?

52
00:10:04,000 --> 00:10:17,440
Speaker 1: Uh, it's, it's depend, it's depend on the scenario. But usually when you start a mission, you will have GPS. Right. most, most of the time,

53
00:10:19,320 --> 00:10:30,240
Speaker 1: GPS will be unavailable in a specific area. So you can assume that you start your mission with GPS and

54
00:10:32,510 --> 00:10:39,550
Speaker 1: maybe a specific location, you will have severe degradation. All right. Fair. Okay.

55
00:10:40,570 --> 00:11:36,470
Speaker 2: Yeah. that's, that's, fair. That's kind of like the assumption we, I was facing around as well, but I just wanted to make sure. Um, we were also thinking of like adding like a ground station. So instead of just the dirt, like the, the UAV itself, we were thinking of, uh, so our drone has a payload underneath with all the sensors that we have. So the drone and the payload are two different things. Um, we were thinking of having a second payload to like kind of active a source of truth within an area. Like kind of, um, like say for example, like the cell tower angle angle that we were looking at, like if we were, if we had a, like that ground station in that area that has connections to these towers, then it could be there to then account for the drift over time because you can't really account for drift when you're, when you're not in range with these towers. So like, would having a ground station or something that's outside of just the drone itself be like a valid part of this solution? Like, is that something that's fair or like, is that just like something that you guys would just completely disregard?

56
00:11:42,620 --> 00:11:50,780
Speaker 2: Um, so we have a ground station to help us like, um, basically like keep in to a ground,

57
00:11:50,960 --> 00:11:51,860
Speaker 1: a ground station,

58
00:11:52,320 --> 00:12:18,180
Speaker 2: so our payload itself, it's just the second payload that would be on the ground. It's just the second payload. Um, I think basically the same sensors for the most part, but like some are cut off because of budget reasons, but, um, the real question is, is I was, I just want to know if like a second device outside of the drone itself, like that's not on your UAV is valid. Like, is that something that you guys would just completely disregard? Is that something that is fine for us to like pursue?

59
00:12:19,180 --> 00:12:21,560
Speaker 1: If you can, if you can, if you can, reliably

60
00:12:21,560 --> 00:12:25,620
Speaker 2: like count on it. Yeah. Yeah. All right.

61
00:12:26,900 --> 00:12:36,400
Speaker 1: If, if, if you can reliably communicate the drones to transmit the drone's location from the ground station to the drones itself. So that's a valid.

62
00:12:36,800 --> 00:12:38,880
Speaker 2: Okay. Yeah. Fair enough. That's fair. All right.

63
00:12:41,400 --> 00:12:54,840
Speaker 2: Um, yeah. Uh, so you also said like to start with location jumps, like, like as like the biggest, like the starting point, I guess, like how, I just want to ask how big are the jumps you typically seeing like real incidents? Like I just, I don't know what to model for here.

64
00:13:12,420 --> 00:13:24,660
Speaker 1: Fair enough. Yeah. Yeah. It's the, most of the time it will be in the range of hundreds. Okay. All right. Um, but it's not, it's not, it's not, it's Okay. It's not

65
00:13:24,660 --> 00:13:49,340
Speaker 2: meters. No, no, no, I was never preparing for meters. I was preparing for like kilometers. I just didn't know like to what scale I wanted to go to. Um, yeah. And I, I guess just beyond jumps then, like, I guess what attack should we start looking into like modeling after that? like what, what matters most in practice? Like, um, I, I guess that's, yeah. Well, what, beyond jumps, like what attacks like matter the most?

66
00:13:55,280 --> 00:14:14,260
Speaker 2: Like I have seen jammers that like specifically like jam only video and like let control go through. I've seen jam, like I've seen jammers do that. I've seen like, um, like a fake, a spoof to GPS, spoofed cell towers. That's the kind of thing we were, I was looking at so far, but I just don't know what really matters because this is just not a problem. I'm not familiar with.

67
00:14:15,160 --> 00:14:17,360
Speaker 1: Yeah. I understand that, but

68
00:14:19,760 --> 00:14:28,900
Speaker 1: doesn't, it doesn't matter that much. I mean, it does, but you need, but you need to, to. You to create function

69
00:14:32,800 --> 00:14:33,620
Speaker 1: that was

70
00:14:39,700 --> 00:14:48,270
Speaker 1: spoofed or not by the different power that you have, or you can extract from, from the different sensor that you have.

71
00:14:48,490 --> 00:14:53,030
Speaker 2: Okay. So you care about like determining if it's spoofed or fake more than how to handle it.

72
00:14:53,150 --> 00:14:53,370
Speaker 1: Yeah.

73
00:14:56,500 --> 00:14:58,040
Speaker 1: Yeah, please. Something

74
00:15:24,120 --> 00:15:27,200
Speaker 1: happened. This is one thing. Okay. The second thing, a

75
00:15:33,340 --> 00:15:51,730
Speaker 1: GPS location needs to be in a specific elevation. I mean, the sky map is known. And sometime, and sometime, if you receive a GPS satellite from a satellite that is not visible,

76
00:15:57,420 --> 00:16:07,510
Speaker 1: spoofed. Okay. I need to drop. I have, I have a different meeting. Yeah. No worries. If you want, you can keep asking questions. We can touch base tomorrow. Yeah.

77
00:16:07,610 --> 00:16:12,630
Speaker 2: I can, I can, I can send some questions later today. No, that's fine. I had to go. I had to go in like 10 minutes anyway.

78
00:16:15,240 --> 00:16:17,880
Speaker 2: All right. No, thank you so much. This helped a lot. Thank you so much.

79
00:16:19,680 --> 00:16:20,280
Speaker 1: All right. Bye.

80
00:16:23,930 --> 00:16:24,250
Speaker 2 [uncertain]: Bye.
